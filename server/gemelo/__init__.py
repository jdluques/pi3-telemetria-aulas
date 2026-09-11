"""Gemelo digital de aulas — bridge ESP32/MQTT -> Gaphor (PI3).

Paquete del lado servidor. Expone la CLI (``python -m gemelo ...``) y los
componentes reutilizables: config, storage, ingest MQTT, sincronización con
Gaphor y generador del modelo.
"""

__version__ = "0.1.0"
