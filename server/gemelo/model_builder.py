"""Generador del modelo Gaphor inicial.

Delega en el backend en **Python puro** (``gaphor_xml.build_model``), que crea el
``.gaphor`` sin la librería de Gaphor (sin GTK), por lo que funciona en cualquier
SO con solo ``uv sync``. Cada bloque de sensor arranca con una value property por
métrica (vacía, "—") en el compartimento "values"; el bridge las rellena.
"""

from __future__ import annotations

from .config import Config
from . import gaphor_xml


def build_model(config: Config, out_path: str | None = None) -> str:
    """Genera el modelo y lo guarda. Devuelve la ruta escrita."""
    return gaphor_xml.build_model(config, out_path)
