# Sensores del gemelo digital

Instrumentación tomada del Excel del proyecto
*"Instrumentación para gemelo digital de ambiente – PI3"*. Se instalan **2
unidades de cada sensor** (una por aula) más **2 ESP32** (uno por aula).

| # | Categoría | Sensor / Modelo | Mide | Interfaz con ESP32 | Métricas (key → unidad) | Evento/alerta |
|---|-----------|-----------------|------|--------------------|--------------------------|----------------|
| 1 | Ruido | **INMP441** | Actividad acústica del aula | I²S | `spl_db` → dB | Ruido elevado / actividad acústica |
| 2 | Calidad de aire / CO₂ | **MH-Z19B** | Concentración de CO₂ (NDIR) | UART/PWM | `co2_ppm` → ppm | CO₂ elevado / ventilación insuficiente |
| 3 | Termodinámica | **BME280** | Temperatura, humedad, presión | I²C/SPI | `temp_c` → °C, `hum_pct` → %, `pres_hpa` → hPa | Variable fuera de rango |
| 4 | Lumínico | **BH1750 (GY-302)** | Iluminancia | I²C | `lux` → lux | Iluminación insuficiente/excesiva |
| 5 | Ocupación / Mapeo térmico | **MLX90640 32×24** | Matriz térmica de 768 puntos | I²C | `min_c`,`max_c`,`mean_c` → °C, `occupancy_est` → personas | Presencia / cambio de ocupación |
| — | Procesamiento / IoT | **ESP32 DevKit V1 (ESP-WROOM-32)** | Adquisición y transmisión | WiFi + Bluetooth | (heartbeat) `rssi` → dBm, `uptime_s` → s | Pérdida/recuperación de conexión |

## Notas por sensor

### INMP441 (ruido, I²S)
Micrófono MEMS digital. El ESP32 calcula el nivel a partir del RMS del audio.
El valor `spl_db` es **relativo** salvo que lo calibres contra un sonómetro; la
constante de calibración está en el firmware (`readINMP441`).

### MH-Z19B (CO₂, UART)
Sensor NDIR. Requiere **~3 minutos de calentamiento** tras encender para dar
lecturas estables. Se lee por UART2 del ESP32.

### BME280 (temperatura/humedad/presión, I²C)
El más fácil para empezar. Dirección I²C `0x76` o `0x77`. Es el sensor activado
por defecto en el firmware.

### BH1750 / GY-302 (luz, I²C)
Devuelve iluminancia directamente en lux. Útil para detectar luces encendidas
sin ocupación (cruzando con `occupancy_est`).

### MLX90640 (mapeo térmico / ocupación, I²C)
Cámara térmica de 32×24 = 768 puntos. **No** transmite la imagen: el ESP32
resume el frame en mín/máx/media y una **estimación de ocupación** contando
píxeles por encima de un umbral de temperatura (configurable en el firmware).

Interpretación de las métricas (son temperaturas de **superficie**, no del aire):
- **`max_c` (máxima):** la más útil. Delata presencia de personas (~30–34 °C) o
  una fuente de calor / sobrecalentamiento si es muy alta.
- **`min_c` (mínima):** superficie más fría (ventana/pared fría, corriente).
- **`mean_c` (media):** ~temperatura ambiente; el BME280 la mide con más
  precisión, así que es algo redundante.

En el dashboard, mín/máx/media tienen medidor de color con rangos anchos
pensados para superficies (ajustables en `config.yaml`).

### ESP32 DevKit V1 (gateway)
No es un sensor: es el nodo que lee todo y publica por WiFi/MQTT. Publica un
*heartbeat* en `gemelo/<aula>/esp32` con la intensidad de señal (`rssi`) y el
tiempo encendido (`uptime_s`).

## Correspondencia con el modelo de Gaphor

Cada fila (sensor) de cada aula se representa como un `Block` de SysML llamado,
por defecto, `"<Modelo> (<Nombre del aula>)"` — por ejemplo `BME280 (Aula A)`.
El bridge escribe la última medición **dentro del bloque**, como *value
properties* de SysML (`Temperatura: °C = 23.4`), creándolas automáticamente.
Puedes cambiar el patrón de nombres en `config.yaml → naming` y usar tu propio
diagrama: ver **[MODELO_GAPHOR.md](MODELO_GAPHOR.md)**.
