"""Test end-to-end del bridge SIN broker real.

Simula la llegada de mensajes MQTT inyectándolos por el callback de paho
(``_on_message``) y verifica toda la cadena: parseo -> SQLite -> Gaphor.
Así se prueba el pegamento completo sin depender de una red ni de Mosquitto.
"""

import json
from datetime import datetime, timezone

import pytest

pytest.importorskip("gaphor")

from gemelo.config import Config
from gemelo.bridge import Bridge
from gemelo.model_builder import build_model
from gemelo.gaphor_sync import GaphorModel


class _FakeMsg:
    """Imita el objeto MQTTMessage de paho (solo lo que usamos)."""
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload.encode() if isinstance(payload, str) else payload


def test_flujo_completo_mqtt_a_gaphor(tmp_path):
    cfg = Config()
    cfg.model_path = str(tmp_path / "modelo.gaphor")
    cfg.db_path = ":memory:"
    build_model(cfg)

    bridge = Bridge(cfg)
    try:
        ts = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc).timestamp()

        # Llega un mensaje de un sensor real -> debe guardarse.
        bridge.ingest._on_message(None, None, _FakeMsg(
            "gemelo/aula-A/bme280",
            json.dumps({"ts": ts, "metrics": {"temp_c": 26.1, "hum_pct": 60,
                                              "pres_hpa": 1009}}),
        ))
        # Llega un heartbeat del ESP32 -> se ignora (no es medición).
        bridge.ingest._on_message(None, None, _FakeMsg(
            "gemelo/aula-A/esp32", json.dumps({"metrics": {"rssi": -55}}),
        ))
        # Llega basura -> se descarta sin romper nada.
        bridge.ingest._on_message(None, None, _FakeMsg(
            "gemelo/aula-A/bme280", "no-json"))

        assert bridge.storage.count() == 3  # 3 métricas del BME280

        result = bridge.sync_now()
        assert "BME280 (Aula A)" in result["updated"]

        model = GaphorModel(cfg.model_path)
        note = model.named_elements()["BME280 (Aula A)"].note
        assert "26.1 °C" in note
    finally:
        bridge.stop()
