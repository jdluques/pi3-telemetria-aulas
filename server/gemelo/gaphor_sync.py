"""Integración con Gaphor: vuelca las últimas mediciones al modelo.

Idea central
------------
El gemelo digital está *modelado* en Gaphor como un diagrama SysML: cada
sensor de cada aula es un ``Block``. Gaphor NO recibe MQTT ni datos en vivo por
sí mismo: es una herramienta de modelado, no un servidor. Lo que hacemos es
abrir el archivo ``.gaphor`` con la API de Python de Gaphor, escribir el último
valor de cada sensor en el campo **Nota** (``note``) de su Block, y volver a
guardar el archivo.

Así, al abrir (o recargar) el modelo en Gaphor, la Nota de cada bloque muestra
la medición actual: ``BME280 (Aula A)`` → "Temperatura: 23.4 °C ...".

El campo ``note`` se eligió porque:
* existe en TODOS los elementos de Gaphor,
* es visible en el panel de propiedades ("Note"),
* admite texto libre y sobrevive al guardar/cargar,
* no exige pelear con el metamodelo de ValueSpecification de SysML.

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
        # Imports perezosos de Gaphor.
        from gaphor.core.modeling import ElementFactory
        from gaphor.core.eventmanager import EventManager
        from gaphor.services.modelinglanguage import ModelingLanguageService
        from gaphor.storage import storage as gaphor_storage
        from gaphor.transaction import Transaction

        self._Transaction = Transaction
        self._storage = gaphor_storage

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
        note = format_note(spec, metrics, ts, sensor)
        model.set_note(element, note)
        updated.append(name)

    if updated:
        model.save()

    return {"updated": updated, "missing": missing}
