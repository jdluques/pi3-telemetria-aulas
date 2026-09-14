"""Integración con Gaphor: vuelca las últimas mediciones al modelo.

Idea central
------------
El gemelo digital está *modelado* en Gaphor como un diagrama SysML: cada
sensor de cada aula es un ``Block``. Gaphor NO recibe MQTT ni datos en vivo por
sí mismo: es una herramienta de modelado, no un servidor. Lo que hacemos es
abrir el archivo ``.gaphor`` con la API de Python de Gaphor, escribir el último
valor de cada sensor y volver a guardar el archivo.

Dónde se escribe el valor (configurable con ``gaphor.display``):

* ``values`` (por defecto): como **value properties** de SysML, DENTRO del
  bloque, en el compartimento "values" (``Temperatura: °C = 23.4``). Es la
  forma idiomática de SysML. El bridge **crea automáticamente** las propiedades
  que falten (una por métrica) y activa el compartimento, así que basta con que
  el bloque tenga el nombre correcto — aunque el diagrama lo haya dibujado el
  alumno a mano. Ver docs/MODELO_GAPHOR.md.
* ``note``: en el campo Nota del elemento (texto libre).
* ``both``: en ambos.

El emparejamiento bloque↔sensor es **por nombre** (ver ``config.naming``).

La escritura al archivo es atómica (archivo temporal + reemplazo) para no
corromper el modelo si algo falla a mitad de camino.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

from .config import Config
from .models import SENSORS, SensorSpec

# Nombre y unidad de la value property que guarda la hora de la última lectura.
UPDATED_LABEL = "Actualizado"
UPDATED_UNIT = "hora"


def format_value(value: float) -> str:
    """Formatea un número para mostrarlo (sin ceros de más): 55.0 -> '55'."""
    return f"{value:g}"


# Marcador que delimita el bloque de datos vivos dentro de la Nota. Todo lo que
# el usuario escriba a mano por ENCIMA del marcador se conserva.
LIVE_MARKER = "── Datos en vivo (gemelo digital) ──"


def format_note(spec: SensorSpec | None, metrics: dict[str, float], ts: datetime,
                sensor_key: str) -> str:
    """Construye el texto legible que se pondrá en la Nota del Block."""
    lines = [LIVE_MARKER]
    ts_local = ts.astimezone()  # muestra en hora local de quien corre el bridge
    lines.append(f"Actualizado: {ts_local:%Y-%m-%d %H:%M:%S %Z}")

    if spec is not None:
        for m in spec.metrics:
            if m.key in metrics:
                lines.append(f"  • {m.label}: {metrics[m.key]:g} {m.unit}")
        # Métricas fuera de la ficha (por si el firmware envía extras).
        extras = [k for k in metrics if spec.metric(k) is None]
    else:
        extras = list(metrics)

    for k in extras:
        lines.append(f"  • {k}: {metrics[k]:g}")

    return "\n".join(lines)


def merge_note(existing: str | None, live_block: str) -> str:
    """Combina la nota existente (parte manual) con el bloque de datos vivos.

    Conserva cualquier texto escrito por el usuario antes del marcador y
    reemplaza (o añade) el bloque de datos vivos.
    """
    existing = existing or ""
    idx = existing.find(LIVE_MARKER)
    manual = existing[:idx].rstrip() if idx != -1 else existing.rstrip()
    if manual:
        return f"{manual}\n\n{live_block}"
    return live_block


class GaphorModel:
    """Abre, modifica y guarda un archivo ``.gaphor``.

    Gaphor se importa de forma perezosa (dentro de ``__init__``) para que el
    resto del paquete se pueda importar/testear aunque Gaphor no esté presente.
    """

    def __init__(self, path: str):
        # Imports perezosos de Gaphor (así el paquete se importa sin Gaphor).
        from gaphor.core.modeling import ElementFactory
        from gaphor.core.eventmanager import EventManager
        from gaphor.services.modelinglanguage import ModelingLanguageService
        from gaphor.storage import storage as gaphor_storage
        from gaphor.transaction import Transaction
        from gaphor.SysML import sysml
        from gaphor.UML import uml as UML
        from gaphor.UML import recipes

        self._Transaction = Transaction
        self._storage = gaphor_storage
        self._sysml = sysml
        self._UML = UML
        self._recipes = recipes
        self._vt_cache: dict[str, object] = {}   # unidad -> ValueType (idempotencia)

        self.path = path
        self.event_manager = EventManager()
        self.modeling_language = ModelingLanguageService(
            event_manager=self.event_manager
        )
        self.element_factory = ElementFactory(self.event_manager)

        with open(path, encoding="utf-8") as f:
            gaphor_storage.load(f, self.element_factory, self.modeling_language)

    def named_elements(self) -> dict[str, object]:
        """Mapa nombre -> elemento, para todos los elementos con nombre."""
        result: dict[str, object] = {}
        for el in self.element_factory.lselect():
            name = getattr(el, "name", None)
            if name:
                result[name] = el
        return result

    def set_note(self, element, text: str) -> None:
        """Escribe la Nota de un elemento dentro de una transacción."""
        with self._Transaction(self.event_manager):
            element.note = merge_note(getattr(element, "note", ""), text)

    # -- value properties (datos dentro del bloque) -----------------------

    def _value_type(self, unit: str):
        """Devuelve el ``ValueType`` de una unidad, reutilizándolo (idempotente)."""
        if unit in self._vt_cache:
            return self._vt_cache[unit]
        for vt in self.element_factory.select(
            lambda e: isinstance(e, self._sysml.ValueType) and e.name == unit
        ):
            self._vt_cache[unit] = vt
            return vt
        vt = self.element_factory.create(self._sysml.ValueType)
        vt.name = unit
        self._vt_cache[unit] = vt
        return vt

    def _get_or_create_property(self, block, label: str, unit: str):
        """Property de valor del bloque, por nombre; la crea si falta.

        Para que aparezca en el compartimento "values" de SysML necesita
        ``type`` = un ValueType y ``aggregation == 'composite'``.
        """
        for p in block.ownedAttribute:
            if p.name == label:
                return p
        prop = self.element_factory.create(self._UML.Property)
        prop.name = label
        prop.type = self._value_type(unit)
        prop.aggregation = "composite"
        block.ownedAttribute = prop
        return prop

    def set_values(self, element, spec: SensorSpec | None,
                   metrics: dict[str, float], ts: datetime) -> bool:
        """Escribe las mediciones como value properties dentro del bloque.

        Crea las propiedades y el ValueType que falten, actualiza su valor y
        activa el compartimento ``show_values`` en todas las presentaciones del
        bloque. Devuelve ``True`` si el elemento admite value properties.
        """
        if not hasattr(element, "ownedAttribute"):
            return False  # el elemento no es un Block/Classifier

        # Orden de métricas: las de la ficha del sensor primero, luego extras.
        items: list[tuple[str, str, float]] = []
        seen = set()
        if spec is not None:
            for m in spec.metrics:
                if m.key in metrics:
                    items.append((m.label, m.unit, metrics[m.key]))
                    seen.add(m.key)
        for k, v in metrics.items():
            if k not in seen:
                items.append((k, "", v))

        with self._Transaction(self.event_manager):
            for label, unit, value in items:
                prop = self._get_or_create_property(element, label, unit)
                self._recipes.set_default_value_from_string(prop, format_value(value))
            # Marca de tiempo, también dentro del bloque.
            upd = self._get_or_create_property(element, UPDATED_LABEL, UPDATED_UNIT)
            self._recipes.set_default_value_from_string(
                upd, f"{ts.astimezone():%H:%M:%S}"
            )
            # Mostrar el compartimento de valores en cada diagrama.
            for pres in element.presentation:
                if hasattr(pres, "show_values"):
                    pres.show_values = True
        return True

    def save(self) -> None:
        """Guarda el modelo de forma atómica en ``self.path``."""
        target = Path(self.path)
        fd, tmp = tempfile.mkstemp(
            dir=str(target.parent), prefix=".gemelo-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                self._storage.save(out, self.element_factory)
            os.replace(tmp, target)  # reemplazo atómico
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def sync(config: Config,
         latest: dict[tuple[str, str], tuple[dict[str, float], datetime]]) -> dict:
    """Vuelca las últimas mediciones al modelo Gaphor indicado en ``config``.

    ``latest`` es lo que devuelve :meth:`Storage.latest_all`.
    Devuelve un pequeño resumen ``{"updated": [...], "missing": [...]}`` útil
    para logs y para los tests.
    """
    display = getattr(config, "display", "values")
    model = GaphorModel(config.model_path)
    by_name = model.named_elements()

    updated: list[str] = []
    missing: list[str] = []

    for (aula, sensor), (metrics, ts) in sorted(latest.items()):
        spec = SENSORS.get(sensor)
        model_label = spec.model if spec else sensor
        name = config.element_name(aula, sensor, model_label)
        element = by_name.get(name)
        if element is None:
            missing.append(name)
            continue
        if display in ("values", "both"):
            model.set_values(element, spec, metrics, ts)
        if display in ("note", "both"):
            model.set_note(element, format_note(spec, metrics, ts, sensor))
        updated.append(name)

    if updated:
        model.save()

    return {"updated": updated, "missing": missing}
