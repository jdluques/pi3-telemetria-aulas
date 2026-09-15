"""Integración con Gaphor: delega en el backend en **Python puro** (gaphor_xml).

El modelo `.gaphor` se genera y actualiza SIN la librería de Gaphor (sin
GTK/PyGObject), por lo que funciona en Linux/macOS/Windows con solo `uv sync`.
Ver ``gaphor_xml.py`` para los detalles del formato.

Se conserva ``GaphorModel`` —que SÍ usa la librería de Gaphor, importada de
forma perezosa— únicamente como utilidad de **lectura para los tests** de
validación (round-trip: comprobar que lo que generamos abre en Gaphor real).
No se usa en el camino de ejecución del bridge.
"""

from __future__ import annotations

from .config import Config
from . import gaphor_xml
# Re-exportados por compatibilidad (los usan tests y el modo display=note).
from .gaphor_xml import (  # noqa: F401
    LIVE_MARKER, UPDATED_LABEL, UPDATED_UNIT,
    format_note, merge_note, format_value,
)


def sync(config: Config, latest: dict) -> dict:
    """Vuelca las últimas mediciones al modelo (backend Python puro).

    ``latest`` = ``{(aula, sensor): (metrics, ts)}`` (ver ``Storage.latest_all``).
    Devuelve ``{"updated": [...], "missing": [...]}``. Propaga
    ``FileNotFoundError`` si el modelo no existe (el bridge lo maneja).
    """
    display = getattr(config, "display", "values")
    return gaphor_xml.update_values(config.model_path, config, latest, display)


class GaphorModel:
    """Lector de un ``.gaphor`` con la librería REAL de Gaphor (solo tests).

    Importa Gaphor de forma perezosa; si no está instalado, lanzará ImportError
    al construirse. Úsese solo como oráculo de validación en las pruebas.
    """

    def __init__(self, path: str):
        from gaphor.core.modeling import ElementFactory
        from gaphor.core.eventmanager import EventManager
        from gaphor.services.modelinglanguage import ModelingLanguageService
        from gaphor.storage import storage as gaphor_storage

        self.path = path
        self.event_manager = EventManager()
        self.modeling_language = ModelingLanguageService(
            event_manager=self.event_manager
        )
        self.element_factory = ElementFactory(self.event_manager)
        with open(path, encoding="utf-8") as f:
            gaphor_storage.load(f, self.element_factory, self.modeling_language)

    def named_elements(self) -> dict[str, object]:
        result: dict[str, object] = {}
        for el in self.element_factory.lselect():
            name = getattr(el, "name", None)
            if name:
                result[name] = el
        return result
