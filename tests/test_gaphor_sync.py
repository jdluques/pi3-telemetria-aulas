"""Tests de la integración con Gaphor (generación de modelo + sincronización).

Requieren Gaphor instalado (está en las dependencias). Si no lo está, se
saltan en vez de fallar.
"""

from datetime import datetime, timezone

import pytest

pytest.importorskip("gaphor")

from gemelo.config import Config
from gemelo.models import SENSORS
from gemelo import gaphor_sync
from gemelo.gaphor_sync import format_note, merge_note, LIVE_MARKER, GaphorModel


# ---- funciones puras (nota; se conservan para el modo display=note) ------

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
    assert manual in merged and live in merged
    merged2 = merge_note(merged, f"{LIVE_MARKER}\nTemperatura: 21 °C")
    assert merged2.count("Notas del profesor") == 1
    assert "21 °C" in merged2 and "20 °C" not in merged2


# ---- helpers -------------------------------------------------------------

def _config(tmp_path) -> Config:
    cfg = Config()
    cfg.model_path = str(tmp_path / "modelo.gaphor")
    cfg.db_path = ":memory:"
    return cfg


def _rendered_properties(block) -> dict:
    """{nombre de property: texto renderizado 'name: Type = value'}."""
    from gaphor.UML.umlfmt import format_property
    return {p.name: format_property(p) for p in block.ownedAttribute}


def _counts(model) -> tuple[int, int]:
    """(nº de Property, nº de ValueType) en el modelo."""
    from gaphor.UML import uml as UML
    from gaphor.SysML import sysml
    ef = model.element_factory
    return (len(ef.lselect(lambda e: isinstance(e, UML.Property))),
            len(ef.lselect(lambda e: isinstance(e, sysml.ValueType))))


# ---- generación del modelo ----------------------------------------------

def test_build_model_crea_bloques_con_value_properties(tmp_path):
    from gemelo.model_builder import build_model
    cfg = _config(tmp_path)
    build_model(cfg)

    model = GaphorModel(cfg.model_path)
    by_name = model.named_elements()
    for aula in cfg.aulas:
        for key, spec in SENSORS.items():
            name = cfg.element_name(aula.id, key, spec.model)
            assert name in by_name
            props = _rendered_properties(by_name[name])
            # Una value property por métrica del sensor.
            for m in spec.metrics:
                assert m.label in props
    # El compartimento de valores está activado en el diagrama.
    bme = by_name[cfg.element_name("aula-A", "bme280", "BME280")]
    assert any(getattr(p, "show_values", 0) for p in bme.presentation)


# ---- sincronización: valores dentro del bloque ---------------------------

def test_sync_escribe_valores_en_el_bloque(tmp_path):
    from gemelo.model_builder import build_model
    cfg = _config(tmp_path)
    build_model(cfg)

    ts = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    latest = {("aula-A", "bme280"): ({"temp_c": 24.7, "hum_pct": 51.0,
                                       "pres_hpa": 1011.0}, ts)}
    result = gaphor_sync.sync(cfg, latest)
    assert result["updated"] == ["BME280 (Aula A)"]
    assert result["missing"] == []

    # Reabrir y comprobar que el valor quedó en la value property.
    model = GaphorModel(cfg.model_path)
    block = model.named_elements()["BME280 (Aula A)"]
    props = _rendered_properties(block)
    assert "24.7" in props["Temperatura"]
    assert "°C" in props["Temperatura"]
    assert "51" in props["Humedad relativa"]
    assert gaphor_sync.UPDATED_LABEL in props        # marca de tiempo
    assert any(getattr(p, "show_values", 0) for p in block.presentation)


def test_sync_es_idempotente(tmp_path):
    from gemelo.model_builder import build_model
    cfg = _config(tmp_path)
    build_model(cfg)
    ts = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

    gaphor_sync.sync(cfg, {("aula-A", "bme280"): ({"temp_c": 20.0}, ts)})
    after1 = _counts(GaphorModel(cfg.model_path))
    # Segunda y tercera sincronización con otros valores.
    gaphor_sync.sync(cfg, {("aula-A", "bme280"): ({"temp_c": 21.0}, ts)})
    gaphor_sync.sync(cfg, {("aula-A", "bme280"): ({"temp_c": 22.0}, ts)})
    after3 = _counts(GaphorModel(cfg.model_path))

    assert after1 == after3          # no se duplican properties ni value types
    block = GaphorModel(cfg.model_path).named_elements()["BME280 (Aula A)"]
    assert "22" in _rendered_properties(block)["Temperatura"]


def test_sync_autocrea_properties_en_bloque_dibujado_a_mano(tmp_path):
    """Un bloque con el nombre correcto pero SIN properties -> se crean solas."""
    path = str(tmp_path / "a_mano.gaphor")
    _make_bare_model(path, "BME280 (Aula A)")

    cfg = _config(tmp_path)
    cfg.model_path = path
    ts = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    result = gaphor_sync.sync(cfg, {("aula-A", "bme280"):
                                    ({"temp_c": 23.1, "hum_pct": 60.0}, ts)})
    assert result["updated"] == ["BME280 (Aula A)"]

    block = GaphorModel(path).named_elements()["BME280 (Aula A)"]
    props = _rendered_properties(block)
    assert "23.1" in props["Temperatura"]
    assert "60" in props["Humedad relativa"]
    assert any(getattr(p, "show_values", 0) for p in block.presentation)


def test_sync_reporta_bloque_faltante(tmp_path):
    from gemelo.model_builder import build_model
    cfg = _config(tmp_path)
    build_model(cfg)
    latest = {("aula-Z", "bme280"): ({"temp_c": 20.0}, datetime.now(timezone.utc))}
    result = gaphor_sync.sync(cfg, latest)
    assert result["updated"] == []
    assert result["missing"] == ["BME280 (aula-Z)"]


def test_sync_modo_note(tmp_path):
    """display=note debe seguir escribiendo en la Nota (compatibilidad)."""
    from gemelo.model_builder import build_model
    cfg = _config(tmp_path)
    cfg.display = "note"
    build_model(cfg)
    ts = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    gaphor_sync.sync(cfg, {("aula-A", "bme280"): ({"temp_c": 24.7}, ts)})
    block = GaphorModel(cfg.model_path).named_elements()["BME280 (Aula A)"]
    assert "24.7 °C" in block.note and LIVE_MARKER in block.note


# ---- utilidad: crea un .gaphor con un bloque nombrado y sin properties ---

def _make_bare_model(path: str, block_name: str) -> None:
    from gaphor.core.modeling import ElementFactory, Diagram
    from gaphor.core.eventmanager import EventManager
    from gaphor.services.modelinglanguage import ModelingLanguageService
    from gaphor.storage import storage
    from gaphor.transaction import Transaction
    from gaphor.SysML import sysml
    from gaphor.diagram.drop import drop

    em = EventManager()
    ml = ModelingLanguageService(event_manager=em)
    ef = ElementFactory(em)
    with Transaction(em):
        d = ef.create(Diagram); d.name = "D"
        b = ef.create(sysml.Block); b.name = block_name
        drop(b, d, x=20, y=20)
    with open(path, "w", encoding="utf-8") as out:
        storage.save(out, ef)
