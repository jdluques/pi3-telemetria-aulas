// ===========================================================================
//  config.h  —  Configuración del ESP32 para el gemelo digital de aulas (PI3)
// ---------------------------------------------------------------------------
//  1. Copia este archivo como  config.h  (en la misma carpeta).
//  2. Rellena tu red WiFi, la IP del broker MQTT y el ID del aula.
//  3. NO subas config.h a Git si contiene contraseñas reales.
// ===========================================================================
#pragma once

// --- WiFi ---------------------------------------------------------------
#define WIFI_SSID       "NombreDeTuWiFi"
#define WIFI_PASSWORD   "TuContraseñaWiFi"

// --- Broker MQTT --------------------------------------------------------
// IP del computador donde corre Mosquitto (mira GUIA_DE_USO.md para saber
// cómo obtenerla). El puerto por defecto de MQTT es 1883.
#define MQTT_HOST       "192.168.1.100"
#define MQTT_PORT       1883
#define MQTT_USER       ""     // deja "" si tu broker no pide usuario
#define MQTT_PASSWORD   ""

// --- Identidad de este ESP32 --------------------------------------------
// Cada aula tiene su propio ESP32. Cambia AULA_ID en cada dispositivo:
//   "aula-A"  para el ESP32 del Aula A
//   "aula-B"  para el ESP32 del Aula B
#define AULA_ID         "aula-A"

// Prefijo de los topics (debe coincidir con base_topic del config.yaml).
#define BASE_TOPIC      "gemelo"

// Cada cuántos milisegundos leer y publicar los sensores.
#define PUBLISH_PERIOD_MS   5000
