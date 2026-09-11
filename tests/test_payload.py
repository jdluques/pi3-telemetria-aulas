"""Tests del contrato de datos: parseo de topics y payloads MQTT."""

import json
from datetime import timezone

import pytest

from gemelo.models import parse_payload, parse_topic, PayloadError, SENSORS


def test_catalogo_tiene_los_sensores_del_excel():
    assert set(SENSORS) == {"inmp441", "mhz19b", "bme280", "bh1750", "mlx90640"}


def test_parse_topic_valido():
    assert parse_topic("gemelo/aula-A/bme280") == ("aula-A", "bme280")


@pytest.mark.parametrize("topic", [
    "gemelo/aula-A",             # faltan partes
    "otro/aula-A/bme280",        # prefijo incorrecto
    "gemelo//bme280",            # aula vacía
    "gemelo/aula-A/bme280/x",    # sobran partes
])
def test_parse_topic_invalido(topic):
    with pytest.raises(PayloadError):
        parse_topic(topic)


def test_parse_payload_completo():
    raw = json.dumps({
        "aula": "aula-A", "sensor": "bme280", "ts": 1725974400,
        "metrics": {"temp_c": 23.4, "hum_pct": 55, "pres_hpa": 1013.2},
    })
    r = parse_payload("gemelo/aula-A/bme280", raw)
    assert r.aula == "aula-A"
    assert r.sensor == "bme280"
    assert r.metrics["temp_c"] == 23.4
    assert r.ts.tzinfo == timezone.utc
    assert r.spec.model == "BME280"


def test_parse_payload_toma_aula_y_sensor_del_topic():
    # Si el cuerpo no trae aula/sensor, se usan los del topic.
    r = parse_payload("gemelo/aula-B/bh1750", '{"metrics": {"lux": 320.5}}')
    assert r.aula == "aula-B"
    assert r.sensor == "bh1750"
    assert r.metrics["lux"] == 320.5


def test_parse_payload_ts_iso():
    r = parse_payload(
        "gemelo/aula-A/bme280",
        '{"ts": "2026-09-10T12:00:00Z", "metrics": {"temp_c": 20}}',
    )
    assert r.ts.year == 2026 and r.ts.hour == 12


def test_parse_payload_sin_metrics_falla():
    with pytest.raises(PayloadError):
        parse_payload("gemelo/aula-A/bme280", '{"ts": 1}')


def test_parse_payload_metric_no_numerica_falla():
    with pytest.raises(PayloadError):
        parse_payload("gemelo/aula-A/bme280", '{"metrics": {"temp_c": "hola"}}')


def test_parse_payload_json_invalido_falla():
    with pytest.raises(PayloadError):
        parse_payload("gemelo/aula-A/bme280", "esto no es json")
