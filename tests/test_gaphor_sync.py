"""Tests de la integración con Gaphor (generación de modelo + sincronización).

Requieren Gaphor instalado (está en requirements.txt). Si no lo está, se
saltan en vez de fallar.
"""

from datetime import datetime, timezone

import pytest

pytest.importorskip("gaphor")

from gemelo.config import Config
from gemelo.models import SENSORS
from gemelo import gaphor_sync
from gemelo.gaphor_sync import format_note, merge_note, LIVE_MARKER, GaphorModel
from gemelo.model_builder import build_model


# ---- funciones puras (no necesitan abrir un modelo) ----------------------

def test_format_note_incluye_metricas_y_unidades():
    spec = SENSORS["bme280"]
    ts = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    note = format_note(spec, {"temp_c": 23.4, "hum_pct": 55.0, "pres_hpa": 1013.0},
                       ts, "bme280")
    assert LIVE_MARKER in note
    assert "Temperatura: 23.4 °C" in note
    assert "Humedad relativa: 55 %" in note


def test_merge_note_conserva_texto_manual():
    manual = "Notas del profesor: revisar calibración."
    live = f"{LIVE_MARKER}\nTemperatura: 20 °C"
    merged = merge_note(manual, live)
    assert manual in merged
    assert live in merged
    # Al re-sincronizar, no se duplica la parte manual.
    merged2 = merge_note(merged, f"{LIVE_MARKER}\nTemperatura: 21 °C")
    assert merged2.count("Notas del profesor") == 1
    assert "21 °C" in merged2 and "20 °C" not in merged2


# ---- integración real con un archivo .gaphor -----------------------------

def _config(tmp_path) -> Config:
    cfg = Config()
    cfg.model_path = str(tmp_path / "modelo.gaphor")
    cfg.db_path = ":memory:"
    return cfg


def test_build_model_crea_bloques_por_sensor(tmp_path):
    cfg = _config(tmp_path)
    build_model(cfg)

    model = GaphorModel(cfg.model_path)
    names = set(model.named_elements())
    # Un bloque por (aula, sensor) con el nombre esperado por el config.
    for aula in cfg.aulas:
        for key, spec in SENSORS.items():
            assert cfg.element_name(aula.id, key, spec.model) in names


def test_sync_escribe_medicion_en_la_nota(tmp_path):
    cfg = _config(tmp_path)
    build_model(cfg)

    ts = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    latest = {("aula-A", "bme280"): ({"temp_c": 24.7, "hum_pct": 51.0,
                                       "pres_hpa": 1011.0}, ts)}
    result = gaphor_sync.sync(cfg, latest)

    assert result["updated"] == ["BME280 (Aula A)"]
    assert result["missing"] == []

    # Reabrir el modelo y comprobar que la nota persiste con el valor.
    model = GaphorModel(cfg.model_path)
    block = model.named_elements()["BME280 (Aula A)"]
    assert "24.7 °C" in block.note
    assert LIVE_MARKER in block.note


def test_sync_reporta_bloque_faltante(tmp_path):
    cfg = _config(tmp_path)
    build_model(cfg)
    # Un sensor en un aula que no existe en el modelo.
    latest = {("aula-Z", "bme280"): ({"temp_c": 20.0}, datetime.now(timezone.utc))}
    result = gaphor_sync.sync(cfg, latest)
    assert result["updated"] == []
    assert result["missing"] == ["BME280 (aula-Z)"]
