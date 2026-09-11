"""Interfaz de línea de comandos del gemelo digital.

Uso general:  ``python -m gemelo <subcomando> [opciones]``

Subcomandos:
  run          Arranca el bridge (MQTT -> SQLite -> Gaphor). Uso normal.
  init-model   Genera el archivo .gaphor inicial con todos los bloques.
  sync-once    Vuelca las últimas mediciones al modelo una sola vez y sale.
  simulate     Publica datos simulados por MQTT (para probar sin hardware).
  latest       Muestra en consola las últimas mediciones guardadas.
  dashboard    Sirve un dashboard web en vivo (http://localhost:8080).
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_config


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Bridge del gemelo digital de aulas (ESP32/MQTT -> Gaphor).",
    )
    p.add_argument("-c", "--config", default="config.yaml",
                   help="Ruta del archivo de configuración YAML (default: config.yaml)")
    p.add_argument("-v", "--verbose", action="store_true", help="Logs detallados")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Arranca el bridge (uso normal).")

    pm = sub.add_parser("init-model", help="Genera el modelo .gaphor inicial.")
    pm.add_argument("-o", "--output", help="Ruta de salida (default: model_path del config)")
    pm.add_argument("--force", action="store_true",
                    help="Sobrescribe el modelo si ya existe.")

    sub.add_parser("sync-once", help="Sincroniza el modelo una vez y sale.")

    ps = sub.add_parser("simulate", help="Publica datos simulados por MQTT.")
    ps.add_argument("--interval", type=float, default=3.0,
                    help="Segundos entre rondas de datos (default: 3)")
    ps.add_argument("--count", type=int, default=0,
                    help="Número de rondas (0 = infinito)")

    sub.add_parser("latest", help="Muestra las últimas mediciones guardadas.")

    pd = sub.add_parser("dashboard", help="Sirve el dashboard web en vivo.")
    pd.add_argument("--host", default="0.0.0.0",
                    help="Interfaz de escucha (default: 0.0.0.0 = toda la red)")
    pd.add_argument("--port", type=int, default=8080, help="Puerto (default: 8080)")
    return p


def cmd_run(cfg) -> int:
    from .bridge import Bridge
    Bridge(cfg).run()
    return 0


def cmd_init_model(cfg, output: str | None, force: bool) -> int:
    from pathlib import Path
    from .model_builder import build_model
    out = output or cfg.model_path
    if Path(out).exists() and not force:
        print(f"[!] El modelo '{out}' ya existe. Usa --force para sobrescribir.")
        return 1
    written = build_model(cfg, out)
    print(f"[ok] Modelo generado en: {written}")
    print(f"    Ábrelo con Gaphor:  uv run gaphor {written}")
    return 0


def cmd_sync_once(cfg) -> int:
    from . import gaphor_sync
    from .storage import Storage
    with Storage(cfg.db_path) as st:
        result = gaphor_sync.sync(cfg, st.latest_all())
    print(f"[ok] Bloques actualizados: {len(result['updated'])}")
    for name in result["updated"]:
        print(f"     ✓ {name}")
    if result["missing"]:
        print("[!] Sin bloque correspondiente en el modelo:")
        for name in result["missing"]:
            print(f"     ✗ {name}")
    return 0


def cmd_simulate(cfg, interval: float, count: int) -> int:
    from .tools_simulate import run_simulator
    return run_simulator(cfg, interval=interval, count=count)


def cmd_latest(cfg) -> int:
    from .storage import Storage
    from .models import SENSORS
    with Storage(cfg.db_path) as st:
        latest = st.latest_all()
    if not latest:
        print("(sin datos todavía)")
        return 0
    for (aula, sensor), (metrics, ts) in sorted(latest.items()):
        spec = SENSORS.get(sensor)
        model = spec.model if spec else sensor
        print(f"\n{aula}  |  {model} ({sensor})  @ {ts.astimezone():%Y-%m-%d %H:%M:%S}")
        for k, v in metrics.items():
            m = spec.metric(k) if spec else None
            unit = f" {m.unit}" if m else ""
            label = m.label if m else k
            print(f"    {label}: {v:g}{unit}")
    return 0


def cmd_dashboard(cfg, host: str, port: int) -> int:
    from .dashboard import run_dashboard
    return run_dashboard(cfg, host=host, port=port)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    cfg = load_config(args.config)

    if args.command == "run":
        return cmd_run(cfg)
    if args.command == "init-model":
        return cmd_init_model(cfg, args.output, args.force)
    if args.command == "sync-once":
        return cmd_sync_once(cfg)
    if args.command == "simulate":
        return cmd_simulate(cfg, args.interval, args.count)
    if args.command == "latest":
        return cmd_latest(cfg)
    if args.command == "dashboard":
        return cmd_dashboard(cfg, args.host, args.port)
    return 2


if __name__ == "__main__":
    sys.exit(main())
