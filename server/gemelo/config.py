"""Carga de configuración del bridge (archivo YAML + variables de entorno).

Un solo archivo YAML describe: dónde está el broker MQTT, dónde está el
modelo de Gaphor a actualizar, cada cuánto sincronizar, y qué aulas existen.
Todos los valores tienen un default razonable para que "arranque solo".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - yaml es dependencia declarada
    yaml = None


@dataclass
class AulaCfg:
    id: str            # id técnico usado en topics, p. ej. "aula-A"
    name: str          # nombre legible, p. ej. "Aula A - Lab. IoT"


@dataclass
class Config:
    # --- MQTT ---
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    base_topic: str = "gemelo"

    # --- Almacenamiento e integración con Gaphor ---
    db_path: str = "gemelo.sqlite3"
    model_path: str = "model/gemelo_aulas.gaphor"
    sync_interval: float = 10.0          # segundos entre escrituras al modelo

    # --- Aulas ---
    aulas: list[AulaCfg] = field(default_factory=lambda: [
        AulaCfg("aula-A", "Aula A"),
        AulaCfg("aula-B", "Aula B"),
    ])

    # Plantilla para el nombre del Block de Gaphor que representa un sensor.
    # Variables disponibles: {model}, {aula_name}, {aula_id}, {sensor}.
    element_name_template: str = "{model} ({aula_name})"

    # Overrides explícitos (aula_id, sensor_key) -> nombre exacto del Block.
    element_overrides: dict[tuple[str, str], str] = field(default_factory=dict)

    # Sobreescrituras de umbrales por métrica (los defaults viven en
    # thresholds.DEFAULTS). Formato: {metric_key: {campo: valor}}.
    thresholds: dict[str, dict] = field(default_factory=dict)

    def aula_name(self, aula_id: str) -> str:
        for a in self.aulas:
            if a.id == aula_id:
                return a.name
        return aula_id

    def element_name(self, aula_id: str, sensor_key: str, model: str) -> str:
        """Nombre del elemento Gaphor que corresponde a un (aula, sensor)."""
        override = self.element_overrides.get((aula_id, sensor_key))
        if override:
            return override
        return self.element_name_template.format(
            model=model,
            aula_name=self.aula_name(aula_id),
            aula_id=aula_id,
            sensor=sensor_key,
        )


def _apply_env(cfg: Config) -> Config:
    """Permite sobreescribir puntos clave con variables de entorno.

    Útil en despliegues/CI sin tocar el YAML. Ejemplo:
    ``GEMELO_MQTT_HOST=192.168.1.50``.
    """
    cfg.mqtt_host = os.environ.get("GEMELO_MQTT_HOST", cfg.mqtt_host)
    if "GEMELO_MQTT_PORT" in os.environ:
        cfg.mqtt_port = int(os.environ["GEMELO_MQTT_PORT"])
    cfg.mqtt_username = os.environ.get("GEMELO_MQTT_USER", cfg.mqtt_username)
    cfg.mqtt_password = os.environ.get("GEMELO_MQTT_PASS", cfg.mqtt_password)
    cfg.model_path = os.environ.get("GEMELO_MODEL_PATH", cfg.model_path)
    cfg.db_path = os.environ.get("GEMELO_DB_PATH", cfg.db_path)
    return cfg


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Carga la configuración desde YAML (si existe) + entorno.

    Si ``path`` es ``None`` o el archivo no existe, se usan los defaults.
    """
    cfg = Config()

    if path is not None:
        p = Path(path)
        if p.exists():
            if yaml is None:
                raise RuntimeError(
                    "Falta PyYAML: ejecuta 'uv sync' en server/ (o 'pip install pyyaml')."
                )
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            _merge(cfg, data)

    return _apply_env(cfg)


def _merge(cfg: Config, data: dict) -> None:
    """Vuelca el diccionario del YAML sobre el objeto Config."""
    mqtt = data.get("mqtt", {}) or {}
    cfg.mqtt_host = mqtt.get("host", cfg.mqtt_host)
    cfg.mqtt_port = int(mqtt.get("port", cfg.mqtt_port))
    cfg.mqtt_username = mqtt.get("username", cfg.mqtt_username)
    cfg.mqtt_password = mqtt.get("password", cfg.mqtt_password)
    cfg.base_topic = mqtt.get("base_topic", cfg.base_topic)

    cfg.db_path = data.get("db_path", cfg.db_path)
    cfg.model_path = data.get("model_path", cfg.model_path)
    cfg.sync_interval = float(data.get("sync_interval", cfg.sync_interval))

    if "aulas" in data and data["aulas"]:
        cfg.aulas = [AulaCfg(a["id"], a.get("name", a["id"])) for a in data["aulas"]]

    naming = data.get("naming", {}) or {}
    cfg.element_name_template = naming.get("template", cfg.element_name_template)
    overrides = naming.get("overrides", []) or []
    cfg.element_overrides = {
        (o["aula"], o["sensor"]): o["element"] for o in overrides
    }

    cfg.thresholds = data.get("thresholds", {}) or {}
