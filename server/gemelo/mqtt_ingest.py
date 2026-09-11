"""Suscriptor MQTT: recibe los mensajes de los ESP32 y los entrega al bridge.

Usa paho-mqtt. Se suscribe a ``<base_topic>/#`` y, por cada mensaje válido,
llama a un callback con el :class:`Reading` ya parseado. Los mensajes que no
cumplen el contrato se ignoran con un log (no tumban el proceso).
"""

from __future__ import annotations

import logging
from typing import Callable

import paho.mqtt.client as mqtt

from .config import Config
from .models import Reading, PayloadError, parse_payload, ESP32_KEY, parse_topic

log = logging.getLogger("gemelo.mqtt")

OnReading = Callable[[Reading], None]


def _make_client(client_id: str):
    """Crea un cliente paho compatible con paho-mqtt 1.x y 2.x.

    En 2.x hay que indicar la versión de la API de callbacks; en 1.x ese
    parámetro no existe. Se usa la v2 si está disponible.
    """
    version = getattr(mqtt, "CallbackAPIVersion", None)
    if version is not None:  # paho-mqtt >= 2.0
        return mqtt.Client(
            callback_api_version=version.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
    return mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)  # paho 1.x


class MqttIngest:
    def __init__(self, config: Config, on_reading: OnReading):
        self.config = config
        self.on_reading = on_reading
        self.client = _make_client("gemelo-bridge")
        if config.mqtt_username:
            self.client.username_pw_set(config.mqtt_username, config.mqtt_password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    # -- callbacks de paho -------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code=0, properties=None):
        # 'reason_code' es int (paho 1.x) o ReasonCode (paho 2.x); 0 / "Success"
        # significan conexión correcta en ambos casos.
        ok = (reason_code == 0) or (getattr(reason_code, "value", None) == 0)
        if ok:
            topic = f"{self.config.base_topic}/#"
            client.subscribe(topic, qos=1)
            log.info("Conectado al broker; suscrito a %s", topic)
        else:
            log.error("Fallo de conexión MQTT (rc=%s)", reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            # El heartbeat del ESP32 (gemelo/<aula>/esp32) no es una medición
            # de sensor: se registra pero no se procesa como Reading.
            _, sensor = parse_topic(msg.topic, self.config.base_topic)
            if sensor == ESP32_KEY:
                log.debug("Heartbeat ESP32 en %s: %s", msg.topic, msg.payload)
                return
            reading = parse_payload(msg.topic, msg.payload, self.config.base_topic)
        except PayloadError as exc:
            log.warning("Mensaje descartado (%s): %s", msg.topic, exc)
            return
        try:
            self.on_reading(reading)
        except Exception:  # pragma: no cover - no dejar caer el hilo de red
            log.exception("Error procesando lectura de %s", msg.topic)

    # -- ciclo de vida -----------------------------------------------------

    def start(self) -> None:
        """Conecta y arranca el loop de red en un hilo de fondo."""
        log.info("Conectando a MQTT %s:%s ...",
                 self.config.mqtt_host, self.config.mqtt_port)
        self.client.connect(self.config.mqtt_host, self.config.mqtt_port, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        try:
            self.client.disconnect()
        except Exception:
            pass
