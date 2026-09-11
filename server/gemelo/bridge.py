"""Bridge: une ingest MQTT + almacenamiento + sincronización con Gaphor.

Flujo:

    ESP32 --(WiFi/MQTT)--> broker --> MqttIngest --> Storage (SQLite)
                                                        |
                             cada 'sync_interval' seg.  v
                                              gaphor_sync.sync() --> modelo .gaphor

El guardado del modelo se hace en un hilo temporizador aparte para no bloquear
la recepción de mensajes y para agrupar varias lecturas en una sola escritura
al archivo (Gaphor no está pensado para escrituras a alta frecuencia).
"""

from __future__ import annotations

import logging
import threading

from . import gaphor_sync
from .config import Config
from .mqtt_ingest import MqttIngest
from .models import Reading
from .storage import Storage

log = logging.getLogger("gemelo.bridge")


class Bridge:
    def __init__(self, config: Config):
        self.config = config
        self.storage = Storage(config.db_path)
        self.ingest = MqttIngest(config, self._on_reading)
        self._stop = threading.Event()
        self._timer: threading.Thread | None = None

    def _on_reading(self, reading: Reading) -> None:
        self.storage.insert(reading)
        log.info("Lectura %s/%s: %s",
                 reading.aula, reading.sensor, reading.metrics)

    def _sync_loop(self) -> None:
        while not self._stop.is_set():
            # Espera interrumpible: si piden parar, sale de inmediato.
            self._stop.wait(self.config.sync_interval)
            if self._stop.is_set():
                break
            self.sync_now()

    def sync_now(self) -> dict:
        """Fuerza una sincronización inmediata con el modelo Gaphor."""
        try:
            result = gaphor_sync.sync(self.config, self.storage.latest_all())
            if result["updated"]:
                log.info("Modelo actualizado: %s", ", ".join(result["updated"]))
            if result["missing"]:
                log.warning(
                    "Sensores sin bloque en el modelo (revisa nombres): %s",
                    ", ".join(result["missing"]),
                )
            return result
        except FileNotFoundError:
            log.error(
                "No existe el modelo '%s'. Genéralo con: python -m gemelo init-model",
                self.config.model_path,
            )
            return {"updated": [], "missing": []}
        except Exception:
            log.exception("Error sincronizando con Gaphor")
            return {"updated": [], "missing": []}

    def run(self) -> None:
        """Arranca el bridge y bloquea hasta Ctrl-C."""
        self.ingest.start()
        self._timer = threading.Thread(target=self._sync_loop, daemon=True)
        self._timer.start()
        log.info("Bridge en marcha. Sync cada %.0fs. Ctrl-C para salir.",
                 self.config.sync_interval)
        try:
            while not self._stop.is_set():
                self._stop.wait(1.0)
        except KeyboardInterrupt:
            log.info("Interrumpido por el usuario.")
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop.set()
        self.ingest.stop()
        self.storage.close()
