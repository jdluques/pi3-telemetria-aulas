#!/usr/bin/env python3
"""Broker MQTT local en Python puro (amqtt) — para pruebas rápidas.

Sirve para levantar un broker sin instalar Mosquitto. Ideal para la demo con el
simulador cuando todo corre en la misma laptop.

Uso (desde server/, con las dependencias instaladas por 'uv sync'):
    uv run python tools/broker_local.py

Escucha en 0.0.0.0:1883 y acepta conexiones anónimas (como Mosquitto por
defecto). Para producción/uso en red con varias máquinas, se recomienda
Mosquitto (ver docs/GUIA_DE_USO.md).
"""

import asyncio
import logging

from amqtt.broker import Broker

logging.basicConfig(level=logging.WARNING)

CONFIG = {
    "listeners": {"default": {"type": "tcp", "bind": "0.0.0.0:1883"}},
    "sys_interval": 0,
    "auth": {"allow-anonymous": True},
}


async def main() -> None:
    broker = Broker(CONFIG)
    await broker.start()
    print("[broker] MQTT local escuchando en 0.0.0.0:1883  (Ctrl-C para salir)")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[broker] Detenido.")
