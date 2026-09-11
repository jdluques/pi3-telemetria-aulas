"""Generador del modelo Gaphor inicial del gemelo digital.

Crear un ``.gaphor`` a mano es tedioso, así que este módulo lo genera por
código con la API de Gaphor: un ``Block`` SysML por cada aula y un ``Block``
por cada sensor de cada aula, todos colocados en un diagrama para que el
equipo pueda abrirlo y verlo de inmediato.

Cada bloque de sensor arranca con una Nota "sin datos"; el bridge la irá
actualizando con las mediciones reales (ver ``gaphor_sync.py``).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .config import Config
from .models import SENSORS
from .gaphor_sync import LIVE_MARKER


# Distribución del diagrama (coordenadas simples en rejilla).
_AULA_X_GAP = 360      # separación horizontal entre aulas
_SENSOR_Y_GAP = 110    # separación vertical entre sensores
_AULA_Y = 40
_SENSORS_Y0 = 150
_X0 = 60


def build_model(config: Config, out_path: str | None = None) -> str:
    """Genera el modelo y lo guarda. Devuelve la ruta escrita."""
    from gaphor.core.modeling import ElementFactory, Diagram
    from gaphor.core.eventmanager import EventManager
    from gaphor.services.modelinglanguage import ModelingLanguageService
    from gaphor.storage import storage as gaphor_storage
    from gaphor.transaction import Transaction
    from gaphor.SysML import sysml
    from gaphor.diagram.drop import drop

    out_path = out_path or config.model_path
    event_manager = EventManager()
    modeling_language = ModelingLanguageService(event_manager=event_manager)
    factory = ElementFactory(event_manager)

    with Transaction(event_manager):
        pkg = factory.create(sysml.uml.Package) if hasattr(sysml, "uml") else None
        diagram = factory.create(Diagram)
        diagram.name = "Gemelo Digital - Aulas"

        for col, aula in enumerate(config.aulas):
            aula_x = _X0 + col * _AULA_X_GAP

            # Bloque del aula.
            aula_block = factory.create(sysml.Block)
            aula_block.name = f"{aula.name} [{aula.id}]"
            aula_block.note = (
                "Ambiente monitoreado por el gemelo digital.\n"
                f"Identificador MQTT: {aula.id}"
            )
            _try_own(aula_block, pkg)
            drop(aula_block, diagram, x=aula_x, y=_AULA_Y)

            # Un bloque por sensor.
            for row, (key, spec) in enumerate(SENSORS.items()):
                block = factory.create(sysml.Block)
                block.name = config.element_name(aula.id, key, spec.model)
                block.note = _initial_note(spec)
                _try_own(block, pkg)
                drop(
                    block,
                    diagram,
                    x=aula_x,
                    y=_SENSORS_Y0 + row * _SENSOR_Y_GAP,
                )

    _atomic_save(gaphor_storage, factory, out_path)
    return out_path


def _initial_note(spec) -> str:
    metricas = ", ".join(f"{m.label} [{m.unit}]" for m in spec.metrics)
    return (
        f"Sensor {spec.model} — {spec.category}\n"
        f"Interfaz: {spec.interface}\n"
        f"Mide: {metricas}\n\n"
        f"{LIVE_MARKER}\n"
        "Sin datos todavía."
    )


def _try_own(element, pkg) -> None:
    """Intenta colgar el elemento de un Package (mejor organización del árbol).

    Si la versión de Gaphor no expone el atributo esperado, se ignora: el
    elemento simplemente aparecerá en la raíz del modelo.
    """
    if pkg is None:
        return
    for attr in ("package", "owningPackage", "nestingPackage"):
        try:
            setattr(element, attr, pkg)
            return
        except Exception:
            continue


def _atomic_save(gaphor_storage, factory, out_path: str) -> None:
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".gemelo-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            gaphor_storage.save(out, factory)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
