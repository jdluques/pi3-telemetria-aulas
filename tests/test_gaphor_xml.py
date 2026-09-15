"""Tests del backend .gaphor en Python puro (NO requieren la librería Gaphor).

Cubren el escenario Windows/macOS donde Gaphor no está instalado: generar y
actualizar el modelo debe funcionar solo con la biblioteca estándar.
La validación de que esos archivos abren en Gaphor real está en
test_gaphor_sync.py (round-trip, se salta si no hay Gaphor).
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from gemelo.config import Config
from gemelo import gaphor_xml
from gemelo.models import SENSORS

M = "https://gaphor.org/model"
SYSML = "https://gaphor.org/modelinglanguage/SysML"
UML = "https://gaphor.org/modelinglanguage/UML"


def _q(uri, local):
    return f"{{{uri}}}{local}"


def _val(el, local):
    n = el.find(f"{_q(M, local)}/{_q(M, 'val')}")
    return n.text if n is not None else None


def _reflist(el, local):
    f = el.find(_q(M, local))
    if f is None:
        return []
    return [r.get("refid") for r in f.findall(f"{_q(M, 'reflist')}/{_q(M, 'ref')}")]


def _single_ref(el, local):
    n = el.find(f"{_q(M, local)}/{_q(M, 'ref')}")
    return n.get("refid") if n is not None else None


class _Model:
    """Carga un .gaphor y ofrece consultas simples (sin Gaphor)."""

    def __init__(self, path):
        self.model = ET.parse(path).getroot().find(_q(M, "model"))
        self.by_id = {e.get("id"): e for e in self.model if e.get("id")}

    def count(self, uri, local):
        return sum(1 for e in self.model if e.tag == _q(uri, local))

    def block(self, name):
        for e in self.model:
            if e.tag == _q(SYSML, "Block") and _val(e, "name") == name:
                return e
        return None

    def block_values(self, name):
        """{label: valor mostrado} de las value properties del bloque."""
        b = self.block(name)
        out = {}
        for pid in _reflist(b, "ownedAttribute"):
            p = self.by_id.get(pid)
            if p is None or p.tag != _q(UML, "Property"):
                continue
            ls = self.by_id.get(_single_ref(p, "defaultValue"))
            out[_val(p, "name")] = _val(ls, "value") if ls is not None else None
        return out

    def block_items_show_values(self, name):
        b = self.block(name)
        res = []
        for bi_id in _reflist(b, "presentation"):
            bi = self.by_id.get(bi_id)
            res.append(bi.find(_q(M, "show_values")) is not None)
        return res


def _cfg(tmp_path):
    cfg = Config()
    cfg.model_path = str(tmp_path / "m.gaphor")
    return cfg


def test_build_model_estructura(tmp_path):
    cfg = _cfg(tmp_path)
    gaphor_xml.build_model(cfg)
    m = _Model(cfg.model_path)
    # 2 aulas x (1 bloque de aula + 5 sensores) = 12 bloques.
    assert m.count(SYSML, "Block") == 12
    # Cada sensor arranca con una value property por métrica ("—").
    vals = m.block_values("BME280 (Aula A)")
    for metric in SENSORS["bme280"].metrics:
        assert vals[metric.label] == "—"
    # El compartimento de valores está activado en el bloque del sensor.
    assert any(m.block_items_show_values("BME280 (Aula A)"))


def test_update_values_escribe_y_es_idempotente(tmp_path):
    cfg = _cfg(tmp_path)
    gaphor_xml.build_model(cfg)
    ts = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

    r = gaphor_xml.update_values(cfg.model_path, cfg,
                                 {("aula-A", "bme280"): ({"temp_c": 23.4,
                                                          "hum_pct": 55.0}, ts)})
    assert r == {"updated": ["BME280 (Aula A)"], "missing": []}
    vals = _Model(cfg.model_path).block_values("BME280 (Aula A)")
    assert vals["Temperatura"] == "23.4" and vals["Humedad relativa"] == "55"
    assert gaphor_xml.UPDATED_LABEL in vals

    before = _Model(cfg.model_path)
    n_prop = before.count(UML, "Property")
    n_vt = before.count(SYSML, "ValueType")
    gaphor_xml.update_values(cfg.model_path, cfg,
                             {("aula-A", "bme280"): ({"temp_c": 25.9}, ts)})
    gaphor_xml.update_values(cfg.model_path, cfg,
                             {("aula-A", "bme280"): ({"temp_c": 26.1}, ts)})
    after = _Model(cfg.model_path)
    assert after.count(UML, "Property") == n_prop      # no se duplican
    assert after.count(SYSML, "ValueType") == n_vt
    assert after.block_values("BME280 (Aula A)")["Temperatura"] == "26.1"


def test_update_values_bloque_faltante(tmp_path):
    cfg = _cfg(tmp_path)
    gaphor_xml.build_model(cfg)
    r = gaphor_xml.update_values(cfg.model_path, cfg,
                                 {("aula-Z", "bme280"): ({"temp_c": 1.0},
                                                         datetime.now(timezone.utc))})
    assert r["updated"] == [] and r["missing"] == ["BME280 (aula-Z)"]


_BARE = """<?xml version="1.0" encoding="utf-8"?>
<gaphor xmlns="https://gaphor.org/model" xmlns:Core="https://gaphor.org/modelinglanguage/Core" xmlns:UML="https://gaphor.org/modelinglanguage/UML" xmlns:SysML="https://gaphor.org/modelinglanguage/SysML" version="4" gaphor-version="3.3.2">
<model>
<Core:Diagram id="D1"><name><val>D</val></name>
<ownedPresentation><reflist><ref refid="BI1"/></reflist></ownedPresentation></Core:Diagram>
<SysML:Block id="B1"><name><val>MH-Z19B (Aula A)</val></name>
<presentation><reflist><ref refid="BI1"/></reflist></presentation></SysML:Block>
<SysML:BlockItem id="BI1"><matrix><val>(1.0, 0.0, 0.0, 1.0, 10.0, 10.0)</val></matrix>
<diagram><ref refid="D1"/></diagram><subject><ref refid="B1"/></subject></SysML:BlockItem>
</model></gaphor>
"""


def test_update_values_autocrea_en_bloque_dibujado_a_mano(tmp_path):
    """Bloque con nombre correcto pero SIN properties -> se crean solas."""
    path = tmp_path / "hand.gaphor"
    path.write_text(_BARE, encoding="utf-8")
    cfg = _cfg(tmp_path)
    ts = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    r = gaphor_xml.update_values(str(path), cfg,
                                 {("aula-A", "mhz19b"): ({"co2_ppm": 1096.0}, ts)})
    assert r["updated"] == ["MH-Z19B (Aula A)"]
    m = _Model(str(path))
    vals = m.block_values("MH-Z19B (Aula A)")
    assert vals["CO2"] == "1096"
    assert all(m.block_items_show_values("MH-Z19B (Aula A)"))  # show_values activado


def test_display_note(tmp_path):
    cfg = _cfg(tmp_path)
    gaphor_xml.build_model(cfg)
    ts = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
    gaphor_xml.update_values(cfg.model_path, cfg,
                             {("aula-A", "bme280"): ({"temp_c": 24.7}, ts)},
                             display="note")
    note = _val(_Model(cfg.model_path).block("BME280 (Aula A)"), "note")
    assert gaphor_xml.LIVE_MARKER in note and "24.7 °C" in note
