"""Escritor/editor del archivo ``.gaphor`` en **Python puro** (sin la librería
de Gaphor y, por tanto, sin GTK/PyGObject).

¿Por qué? La *librería* de Gaphor arrastra GTK/PyGObject (el toolkit gráfico),
cuya instalación en Windows/macOS es complicada. Pero el ``.gaphor`` es solo un
archivo **XML de datos**, así que aquí lo generamos y editamos con
``xml.etree.ElementTree`` (biblioteca estándar). Resultado: el bridge crea y
actualiza el modelo en **cualquier SO** con solo ``uv sync`` (cero compilación).
La app de escritorio de Gaphor solo se necesita para *ver* el modelo.

El formato es muy regular (``version="4"``): cada elemento tiene ``id`` y las
relaciones son ``<campo><ref refid="..."/></campo>`` o con ``<reflist>``. Los
datos vivos se muestran como *value properties* de SysML dentro del bloque
(compartimento "values"), igual que hacía la versión basada en la librería.

Un test de *round-trip* (ver tests/) carga los archivos que generamos con la
librería real de Gaphor para garantizar que abren correctamente.
"""

from __future__ import annotations

import os
import tempfile
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from .models import SENSORS, SensorSpec

# --- Namespaces del formato .gaphor --------------------------------------
NS = {
    "": "https://gaphor.org/model",
    "Core": "https://gaphor.org/modelinglanguage/Core",
    "UML": "https://gaphor.org/modelinglanguage/UML",
    "SysML": "https://gaphor.org/modelinglanguage/SysML",
}
for _prefix, _uri in NS.items():
    ET.register_namespace(_prefix, _uri)

GAPHOR_FILE_VERSION = "4"          # versión de formato soportada
GAPHOR_VERSION_TAG = "3.3.2"       # informativo (metadato del archivo)
DIAGRAM_NAME = "Gemelo Digital - Aulas"

# Property de la marca de tiempo (dentro del bloque).
UPDATED_LABEL = "Actualizado"
UPDATED_UNIT = "hora"

# Marcador para el modo 'note' (compatibilidad).
LIVE_MARKER = "── Datos en vivo (gemelo digital) ──"

# Distribución del diagrama.
_AULA_X_GAP = 360
_SENSOR_Y_GAP = 120
_AULA_Y = 40
_SENSORS_Y0 = 150
_X0 = 60


def _Q(prefix: str, local: str) -> str:
    return f"{{{NS[prefix]}}}{local}"


def _D(local: str) -> str:
    return f"{{{NS['']}}}{local}"


def new_id() -> str:
    return str(uuid.uuid4())


def format_value(value: float) -> str:
    """Formatea un número para mostrar (sin ceros de más): 55.0 -> '55'."""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# Notas (modo display=note|both). Funciones puras, reutilizadas por gaphor_sync.
# ---------------------------------------------------------------------------

def format_note(spec: SensorSpec | None, metrics: dict[str, float],
                ts: datetime, sensor_key: str = "") -> str:
    lines = [LIVE_MARKER, f"Actualizado: {ts.astimezone():%Y-%m-%d %H:%M:%S %Z}"]
    seen = set()
    if spec is not None:
        for m in spec.metrics:
            if m.key in metrics:
                lines.append(f"  • {m.label}: {metrics[m.key]:g} {m.unit}")
                seen.add(m.key)
    for k, v in metrics.items():
        if k not in seen:
            lines.append(f"  • {k}: {v:g}")
    return "\n".join(lines)


def merge_note(existing: str | None, live_block: str) -> str:
    existing = existing or ""
    idx = existing.find(LIVE_MARKER)
    manual = existing[:idx].rstrip() if idx != -1 else existing.rstrip()
    return f"{manual}\n\n{live_block}" if manual else live_block


# ---------------------------------------------------------------------------
# Helpers de construcción de XML
# ---------------------------------------------------------------------------

def _val(parent, local: str, text: str):
    f = ET.SubElement(parent, _D(local))
    ET.SubElement(f, _D("val")).text = text
    return f


def _ref(parent, local: str, refid: str):
    f = ET.SubElement(parent, _D(local))
    ET.SubElement(f, _D("ref")).set("refid", refid)
    return f


def _reflist(parent, local: str, refids: list[str]):
    f = ET.SubElement(parent, _D(local))
    rl = ET.SubElement(f, _D("reflist"))
    for rid in refids:
        ET.SubElement(rl, _D("ref")).set("refid", rid)
    return f


def _elem(model, prefix: str, local: str, eid: str | None = None):
    e = ET.SubElement(model, _Q(prefix, local))
    if eid:
        e.set("id", eid)
    return e


def _make_block(model, name: str, note: str | None) -> ET.Element:
    b = _elem(model, "SysML", "Block", new_id())
    _val(b, "name", name)
    if note:
        _val(b, "note", note)
    return b


def _make_value_type(model, unit: str, cache: dict[str, str]) -> str:
    if unit in cache:
        return cache[unit]
    vid = new_id()
    vt = _elem(model, "SysML", "ValueType", vid)
    _val(vt, "name", unit)
    cache[unit] = vid
    return vid


def _make_property(model, block_id: str, label: str, vt_id: str,
                   value: str) -> ET.Element:
    """Crea una value property (Property + su LiteralString) y la devuelve."""
    pid = new_id()
    lsid = new_id()
    p = _elem(model, "UML", "Property", pid)
    _val(p, "aggregation", "composite")
    _ref(p, "defaultValue", lsid)
    _val(p, "name", label)
    _ref(p, "structuredClassifier", block_id)
    _ref(p, "type", vt_id)

    ls = _elem(model, "UML", "LiteralString", lsid)
    _val(ls, "name", value)
    _ref(ls, "owningProperty", pid)
    _val(ls, "value", value)
    return p


def _make_block_item(model, diagram_id: str, block_id: str, x: float, y: float,
                     show_values: bool, width: float, height: float) -> str:
    bid = new_id()
    bi = _elem(model, "SysML", "BlockItem", bid)
    _val(bi, "matrix", f"(1.0, 0.0, 0.0, 1.0, {float(x)}, {float(y)})")
    _val(bi, "top-left", "(0.0, 0.0)")
    _val(bi, "width", f"{float(width)}")
    _val(bi, "height", f"{float(height)}")
    _ref(bi, "diagram", diagram_id)
    if show_values:
        _val(bi, "show_values", "1")
    _ref(bi, "subject", block_id)
    return bid


# ---------------------------------------------------------------------------
# Helpers de lectura/edición (para update_values)
# ---------------------------------------------------------------------------

def _get_val(el: ET.Element, local: str) -> str | None:
    node = el.find(f"{_D(local)}/{_D('val')}")
    return node.text if node is not None else None


def _set_val(el: ET.Element, local: str, text: str) -> None:
    field = el.find(_D(local))
    if field is None:
        _val(el, local, text)
        return
    v = field.find(_D("val"))
    if v is None:
        v = ET.SubElement(field, _D("val"))
    v.text = text


def _reflist_ids(el: ET.Element, local: str) -> list[str]:
    field = el.find(_D(local))
    if field is None:
        return []
    return [r.get("refid") for r in field.findall(f"{_D('reflist')}/{_D('ref')}")]


def _extend_reflist(el: ET.Element, local: str, new_ids: list[str]) -> None:
    field = el.find(_D(local))
    if field is None:
        _reflist(el, local, new_ids)
        return
    rl = field.find(_D("reflist"))
    if rl is None:
        rl = ET.SubElement(field, _D("reflist"))
    for rid in new_ids:
        ET.SubElement(rl, _D("ref")).set("refid", rid)


def _single_refid(el: ET.Element, local: str) -> str | None:
    node = el.find(f"{_D(local)}/{_D('ref')}")
    return node.get("refid") if node is not None else None


def _atomic_write(root: ET.Element, out_path: str) -> None:
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".gemelo-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            ET.ElementTree(root).write(f, encoding="utf-8", xml_declaration=True)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _description_note(spec: SensorSpec) -> str:
    metricas = ", ".join(f"{m.label} [{m.unit}]" for m in spec.metrics)
    return (f"Sensor {spec.model} — {spec.category}\n"
            f"Interfaz: {spec.interface}\n"
            f"Mide: {metricas}\n{spec.purpose}")


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def build_model(config, out_path: str | None = None) -> str:
    """Genera el modelo .gaphor inicial (Python puro). Devuelve la ruta."""
    out_path = out_path or config.model_path
    root = ET.Element(_D("gaphor"))
    root.set("version", GAPHOR_FILE_VERSION)
    root.set("gaphor-version", GAPHOR_VERSION_TAG)
    model = ET.SubElement(root, _D("model"))

    _elem(model, "Core", "StyleSheet", new_id())
    diagram_id = new_id()
    diagram = _elem(model, "Core", "Diagram", diagram_id)
    _val(diagram, "name", DIAGRAM_NAME)

    presentation_ids: list[str] = []
    vt_cache: dict[str, str] = {}

    for col, aula in enumerate(config.aulas):
        aula_x = _X0 + col * _AULA_X_GAP

        aula_block = _make_block(
            model, f"{aula.name} [{aula.id}]",
            f"Ambiente monitoreado por el gemelo digital.\nIdentificador MQTT: {aula.id}",
        )
        abi = _make_block_item(model, diagram_id, aula_block.get("id"),
                               aula_x, _AULA_Y, False, 180, 44)
        _reflist(aula_block, "presentation", [abi])
        presentation_ids.append(abi)

        for row, (key, spec) in enumerate(SENSORS.items()):
            name = config.element_name(aula.id, key, spec.model)
            block = _make_block(model, name, _description_note(spec))
            prop_ids = []
            for m in spec.metrics:
                vt = _make_value_type(model, m.unit, vt_cache)
                prop = _make_property(model, block.get("id"), m.label, vt, "—")
                prop_ids.append(prop.get("id"))
            _reflist(block, "ownedAttribute", prop_ids)
            bi = _make_block_item(model, diagram_id, block.get("id"), aula_x,
                                  _SENSORS_Y0 + row * _SENSOR_Y_GAP, True,
                                  220, 44 + 18 * len(prop_ids))
            _reflist(block, "presentation", [bi])
            presentation_ids.append(bi)

    _reflist(diagram, "ownedPresentation", presentation_ids)
    _atomic_write(root, out_path)
    return out_path


def update_values(path: str, config, latest: dict, display: str = "values") -> dict:
    """Escribe las últimas mediciones en el .gaphor existente (Python puro).

    ``latest`` = ``{(aula, sensor): (metrics, ts)}``. Empareja bloques por nombre,
    crea/actualiza value properties (idempotente) y activa ``show_values``.
    Devuelve ``{"updated": [...], "missing": [...]}``.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    model = root.find(_D("model"))

    by_id = {el.get("id"): el for el in model if el.get("id")}
    blocks_by_name: dict[str, ET.Element] = {}
    vt_cache: dict[str, str] = {}
    for el in model:
        if el.tag == _Q("SysML", "Block"):
            nm = _get_val(el, "name")
            if nm:
                blocks_by_name[nm] = el
        elif el.tag == _Q("SysML", "ValueType"):
            nm = _get_val(el, "name")
            if nm:
                vt_cache[nm] = el.get("id")

    updated: list[str] = []
    missing: list[str] = []

    for (aula, sensor), (metrics, ts) in sorted(latest.items()):
        spec = SENSORS.get(sensor)
        model_label = spec.model if spec else sensor
        name = config.element_name(aula, sensor, model_label)
        block = blocks_by_name.get(name)
        if block is None:
            missing.append(name)
            continue

        if display in ("values", "both"):
            _apply_values(model, by_id, block, spec, metrics, ts, vt_cache)
        if display in ("note", "both"):
            live = format_note(spec, metrics, ts, sensor)
            _set_val(block, "note", merge_note(_get_val(block, "note"), live))
        updated.append(name)

    if updated:
        _atomic_write(root, path)
    return {"updated": updated, "missing": missing}


def _apply_values(model, by_id, block, spec, metrics, ts, vt_cache) -> None:
    # Propiedades existentes del bloque, por nombre.
    props_by_name: dict[str, ET.Element] = {}
    for pid in _reflist_ids(block, "ownedAttribute"):
        pe = by_id.get(pid)
        if pe is not None and pe.tag == _Q("UML", "Property"):
            nm = _get_val(pe, "name")
            if nm:
                props_by_name[nm] = pe

    # Lista de (label, unidad, valor): métricas de la ficha, luego extras.
    items: list[tuple[str, str, str]] = []
    seen = set()
    if spec is not None:
        for m in spec.metrics:
            if m.key in metrics:
                items.append((m.label, m.unit, format_value(metrics[m.key])))
                seen.add(m.key)
    for k, v in metrics.items():
        if k not in seen:
            items.append((k, "", format_value(v)))
    items.append((UPDATED_LABEL, UPDATED_UNIT, f"{ts.astimezone():%H:%M:%S}"))

    new_ids = []
    for label, unit, value in items:
        pe = props_by_name.get(label)
        if pe is not None:
            _update_property_value(model, by_id, pe, value)
        else:
            vt = _make_value_type(model, unit, vt_cache)
            prop = _make_property(model, block.get("id"), label, vt, value)
            by_id[prop.get("id")] = prop
            props_by_name[label] = prop
            new_ids.append(prop.get("id"))
    if new_ids:
        _extend_reflist(block, "ownedAttribute", new_ids)

    # Mostrar el compartimento de valores en cada presentación del bloque.
    for bi_id in _reflist_ids(block, "presentation"):
        bi = by_id.get(bi_id)
        if bi is not None and bi.tag == _Q("SysML", "BlockItem"):
            if bi.find(_D("show_values")) is None:
                _val(bi, "show_values", "1")


def _update_property_value(model, by_id, prop: ET.Element, value: str) -> None:
    """Actualiza el LiteralString de defaultValue de una property existente."""
    ls_id = _single_refid(prop, "defaultValue")
    ls = by_id.get(ls_id) if ls_id else None
    if ls is None:
        # No tenía defaultValue: crear un LiteralString y enlazarlo.
        ls_id = new_id()
        field = prop.find(_D("defaultValue"))
        if field is None:
            _ref(prop, "defaultValue", ls_id)
        else:
            ref = field.find(_D("ref"))
            if ref is None:
                ref = ET.SubElement(field, _D("ref"))
            ref.set("refid", ls_id)
        ls = _elem(model, "UML", "LiteralString", ls_id)
        _val(ls, "name", value)
        _ref(ls, "owningProperty", prop.get("id"))
        _val(ls, "value", value)
        by_id[ls_id] = ls
    else:
        _set_val(ls, "name", value)
        _set_val(ls, "value", value)
