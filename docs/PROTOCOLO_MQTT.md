# Protocolo MQTT — contrato entre ESP32 y servidor

Este documento define **exactamente** cómo se comunican el ESP32 (firmware) y
el bridge (servidor). Si ambos respetan este contrato, cualquiera puede
reemplazar una parte sin romper la otra.

## Topics

Estructura fija:

```
<base_topic>/<aula>/<sensor>
```

- `base_topic`: por defecto `gemelo` (configurable en `config.yaml`).
- `aula`: identificador del aula. Debe coincidir con un `id` de la lista
  `aulas` del `config.yaml`. Ej.: `aula-A`, `aula-B`.
- `sensor`: la *key* del sensor (ver tabla). Ej.: `bme280`.

Ejemplos:
```
gemelo/aula-A/bme280
gemelo/aula-A/bh1750
gemelo/aula-B/mhz19b
gemelo/aula-A/esp32      ← heartbeat de estado (no es un sensor)
```

## Formato del mensaje (payload)

**JSON** con esta forma:

```json
{
  "aula": "aula-A",
  "sensor": "bme280",
  "ts": 1725974400,
  "metrics": {
    "temp_c": 23.4,
    "hum_pct": 55.1,
    "pres_hpa": 1013.2
  }
}
```

Reglas:

- `metrics` es **obligatorio** y debe tener al menos un valor **numérico**.
- `aula` y `sensor` son **opcionales** en el cuerpo: si faltan, se toman del
  topic. (Recomendado enviarlos igual, para claridad.)
- `ts` (marca de tiempo) es **opcional**. Acepta:
  - epoch en **segundos** (`1725974400`) o **milisegundos** (`1725974400000`),
  - o texto ISO-8601 (`"2026-09-10T12:00:00Z"`).
  - Si falta, el servidor usa su hora de recepción.
- Los mensajes que no cumplan estas reglas se **descartan con un aviso** en el
  log del bridge (no tumban el proceso).

## Métricas por sensor

| Sensor | `sensor` (key) | Métricas (`metrics`) | Unidad |
|--------|----------------|----------------------|--------|
| INMP441 | `inmp441` | `spl_db` | dB |
| MH-Z19B | `mhz19b` | `co2_ppm` | ppm |
| BME280 | `bme280` | `temp_c`, `hum_pct`, `pres_hpa` | °C, %, hPa |
| BH1750 | `bh1750` | `lux` | lux |
| MLX90640 | `mlx90640` | `min_c`, `max_c`, `mean_c`, `occupancy_est` | °C, °C, °C, personas |
| ESP32 (estado) | `esp32` | `rssi`, `uptime_s` | dBm, s |

> El `MLX90640` **no** envía los 768 píxeles por MQTT; envía magnitudes
> derivadas del frame térmico. `occupancy_est` es una estimación por umbral.

> El topic `esp32` es un *heartbeat*: el servidor lo registra pero **no** lo
> trata como medición de sensor.

## QoS y retención

- El firmware publica con **QoS 1** (entrega al menos una vez).
- No se usa `retain`. Si quieres que un cliente que se conecta tarde reciba el
  último valor, puedes activar `retain=true` en el firmware (opcional).

## Cómo espiar los mensajes (depuración)

```bash
# Ver todo lo que llega al broker:
mosquitto_sub -h localhost -t "gemelo/#" -v

# Publicar un mensaje de prueba a mano:
mosquitto_pub -h localhost -t "gemelo/aula-A/bme280" \
  -m '{"metrics":{"temp_c":21.5,"hum_pct":48,"pres_hpa":1010}}'
```

## Añadir un sensor nuevo

1. Agrega su ficha a `server/gemelo/models.py` en el diccionario `SENSORS`
   (key, modelo, métricas con sus unidades).
2. Regenera el modelo: `uv run gemelo init-model --force`.
3. Haz que el ESP32 publique en `gemelo/<aula>/<nueva-key>` con las métricas
   declaradas.
