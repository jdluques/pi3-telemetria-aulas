"""Almacenamiento histórico de mediciones en SQLite.

SQLite es la "fuente de verdad" del gemelo: guarda TODAS las lecturas con su
marca de tiempo. Gaphor solo muestra el último valor (una foto del estado
actual), pero el histórico completo queda aquí para análisis posterior.

La clase es segura para uso concurrente: el callback de MQTT (un hilo) inserta
mientras el hilo de sincronización lee. Se usa un ``Lock`` y una única conexión
con ``check_same_thread=False``.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .models import Reading


_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,   -- ISO-8601 UTC
    aula    TEXT    NOT NULL,
    sensor  TEXT    NOT NULL,
    metric  TEXT    NOT NULL,
    value   REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_readings_lookup
    ON readings (aula, sensor, metric, ts);
"""


class Storage:
    """Wrapper mínimo sobre SQLite para lecturas de sensores."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        # WAL permite que el dashboard (otro proceso) lea mientras el bridge
        # escribe, sin bloqueos. (No aplica a bases en memoria.)
        if db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- escritura ---------------------------------------------------------

    def insert(self, reading: Reading) -> None:
        """Guarda cada métrica de una lectura como una fila."""
        ts = reading.ts.astimezone(timezone.utc).isoformat()
        rows = [
            (ts, reading.aula, reading.sensor, metric, value)
            for metric, value in reading.metrics.items()
        ]
        with self._lock:
            self._conn.executemany(
                "INSERT INTO readings (ts, aula, sensor, metric, value) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()

    # -- lectura -----------------------------------------------------------

    def latest(self, aula: str, sensor: str) -> tuple[dict[str, float], datetime] | None:
        """Últimos valores de cada métrica de un (aula, sensor).

        Devuelve ``(metrics, ts)`` o ``None`` si aún no hay datos.
        """
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT metric, value, ts
                FROM readings
                WHERE aula = ? AND sensor = ?
                  AND ts = (
                      SELECT MAX(ts) FROM readings
                      WHERE aula = ? AND sensor = ?
                  )
                """,
                (aula, sensor, aula, sensor),
            )
            rows = cur.fetchall()
        if not rows:
            return None
        metrics = {metric: value for metric, value, _ in rows}
        ts = datetime.fromisoformat(rows[0][2])
        return metrics, ts

    def latest_all(self) -> dict[tuple[str, str], tuple[dict[str, float], datetime]]:
        """Últimos valores de todos los (aula, sensor) conocidos.

        Devuelve ``{(aula, sensor): (metrics, ts)}``.
        """
        with self._lock:
            pairs = self._conn.execute(
                "SELECT DISTINCT aula, sensor FROM readings"
            ).fetchall()
        result: dict[tuple[str, str], tuple[dict[str, float], datetime]] = {}
        for aula, sensor in pairs:
            latest = self.latest(aula, sensor)
            if latest is not None:
                result[(aula, sensor)] = latest
        return result

    def history(self, aula: str, sensor: str, metric: str,
                limit: int = 40) -> list[float]:
        """Últimos ``limit`` valores de una métrica, en orden cronológico.

        Se usa para dibujar los sparklines (tendencia reciente) del dashboard.
        """
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT value FROM readings
                WHERE aula = ? AND sensor = ? AND metric = ?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (aula, sensor, metric, limit),
            )
            rows = cur.fetchall()
        return [v for (v,) in reversed(rows)]

    def history_points(self, aula: str, sensor: str, metric: str,
                       limit: int = 500) -> list[dict]:
        """Últimos ``limit`` puntos (ts + valor) de una métrica, cronológicos.

        Se usa para la gráfica histórica en grande del dashboard.
        Devuelve ``[{"ts": <iso>, "v": <float>}, ...]``.
        """
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT ts, value FROM readings
                WHERE aula = ? AND sensor = ? AND metric = ?
                ORDER BY ts DESC
                LIMIT ?
                """,
                (aula, sensor, metric, limit),
            )
            rows = cur.fetchall()
        return [{"ts": ts, "v": v} for ts, v in reversed(rows)]

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # Soporte para 'with Storage(...) as s:'
    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
