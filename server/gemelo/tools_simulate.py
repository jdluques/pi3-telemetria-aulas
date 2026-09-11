"""Simulador de ESP32: publica datos realistas por MQTT.

Sirve para probar TODO el pipeline (broker -> bridge -> Gaphor) sin tener el
hardware conectado. Genera valores plausibles para cada sensor de cada aula.

Se usa desde la CLI (``python -m gemelo simulate``) o de forma directa con
``run_simulator``.
"""

from __future__ import annotations

import json
import logging
import math
import time

import paho.mqtt.client as mqtt

from .config import Config
from .models import SENSORS

log = logging.getLogger("gemelo.simulate")


def _sample(sensor_key: str, tick: int, aula_offset: float) -> dict[str, float]:
    """Valores plausibles y variables en el tiempo para un sensor."""
    # Onda lenta para que los valores "respiren" y se note el cambio en Gaphor.
    wave = math.sin(tick / 5.0)
    if sensor_key == "inmp441":
        return {"spl_db": round(45 + 15 * abs(wave) + aula_offset, 1)}
    if sensor_key == "mhz19b":
        return {"co2_ppm": round(600 + 250 * (wave + 1) + 20 * aula_offset)}
    if sensor_key == "bme280":
        return {
            "temp_c": round(22 + 3 * wave + aula_offset, 2),
            "hum_pct": round(50 + 10 * wave, 1),
            "pres_hpa": round(1012 + 2 * wave, 1),
        }
    if sensor_key == "bh1750":
        return {"lux": round(max(0.0, 300 + 250 * wave + 30 * aula_offset), 1)}
    if sensor_key == "mlx90640":
        occ = max(0, int(round(3 + 2 * wave + aula_offset)))
        return {
            "min_c": round(21 + wave, 2),
            "max_c": round(31 + 3 * abs(wave) + occ * 0.5, 2),
            "mean_c": round(25 + wave, 2),
            "occupancy_est": occ,
        }
    return {}


def _make_client(client_id: str):
    version = getattr(mqtt, "CallbackAPIVersion", None)
    if version is not None:  # paho-mqtt >= 2.0
        return mqtt.Client(callback_api_version=version.VERSION2, client_id=client_id)
    return mqtt.Client(client_id=client_id)


def run_simulator(cfg: Config, interval: float = 3.0, count: int = 0) -> int:
    client = _make_client("gemelo-simulador")
    if cfg.mqtt_username:
        client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password)
    log.info("Simulador conectando a %s:%s ...", cfg.mqtt_host, cfg.mqtt_port)
    client.connect(cfg.mqtt_host, cfg.mqtt_port, keepalive=30)
    client.loop_start()

    print(f"[sim] Publicando datos de {len(cfg.aulas)} aulas x {len(SENSORS)} "
          f"sensores cada {interval}s. Ctrl-C para parar.")
    tick = 0
    try:
        while count == 0 or tick < count:
            for offset, aula in enumerate(cfg.aulas):
                for key in SENSORS:
                    metrics = _sample(key, tick, offset)
                    if not metrics:
                        continue
                    topic = f"{cfg.base_topic}/{aula.id}/{key}"
                    payload = json.dumps({
                        "aula": aula.id,
                        "sensor": key,
                        "ts": time.time(),
                        "metrics": metrics,
                    })
                    client.publish(topic, payload, qos=1)
            print(f"[sim] Ronda {tick + 1} publicada.")
            tick += 1
            if count == 0 or tick < count:
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[sim] Detenido.")
    finally:
        client.loop_stop()
        client.disconnect()
    return 0
