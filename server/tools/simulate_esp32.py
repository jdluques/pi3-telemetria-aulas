#!/usr/bin/env python3
"""Lanza el simulador de ESP32 de forma directa (sin la CLI del paquete).

Ejemplo:
    python tools/simulate_esp32.py --config ../config.yaml --interval 2
"""

import argparse
import sys
from pathlib import Path

# Permite ejecutar el script desde cualquier carpeta encontrando el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gemelo.config import load_config          # noqa: E402
from gemelo.tools_simulate import run_simulator  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Simulador de ESP32 (MQTT).")
    ap.add_argument("-c", "--config", default="config.yaml")
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--count", type=int, default=0)
    args = ap.parse_args()
    cfg = load_config(args.config)
    return run_simulator(cfg, interval=args.interval, count=args.count)


if __name__ == "__main__":
    raise SystemExit(main())
