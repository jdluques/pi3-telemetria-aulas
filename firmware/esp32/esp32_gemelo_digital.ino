// ===========================================================================
//  esp32_gemelo_digital.ino
//  Firmware del ESP32 para el GEMELO DIGITAL DE AULAS (Proyecto PI3)
// ---------------------------------------------------------------------------
//  Qué hace:
//    * Se conecta al WiFi y a un broker MQTT (Mosquitto en un PC local).
//    * Lee los sensores del aula (BME280, BH1750, MH-Z19B, MLX90640, INMP441).
//    * Publica cada medición como JSON en el topic  gemelo/<aula>/<sensor>.
//    * Envía un "heartbeat" con el estado del ESP32.
//
//  El servidor (bridge en Python) recibe estos mensajes y los vuelca al
//  modelo de Gaphor. Ver README.md y docs/PROTOCOLO_MQTT.md.
//
//  IMPORTANTE — activación incremental:
//    Al inicio solo está activado el BME280 (el más sencillo). Activa cada
//    sensor poniendo su ENABLE_* en 1 A MEDIDA que lo conectes y tengas su
//    librería instalada. Así evitas errores de compilación por librerías que
//    aún no usas.
//
//  Librerías (Arduino Library Manager) — instala solo las de los sensores
//  que actives:
//    * PubSubClient           (Nick O'Leary)      -> MQTT
//    * ArduinoJson            (Benoit Blanchon)   -> armar el JSON
//    * Adafruit BME280        (+ Adafruit Unified Sensor)
//    * BH1750                 (Christopher Laws)
//    * MH-Z19                 (Jonathan Dempsey)  -> MH-Z19B por UART
//    * Adafruit MLX90640
//  (INMP441 usa el driver I2S incluido en el core del ESP32.)
// ===========================================================================

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "config.h"          // <-- copia config.example.h a config.h

// --- Activa (1) o desactiva (0) cada sensor ------------------------------
#define ENABLE_BME280    1
#define ENABLE_BH1750    0
#define ENABLE_MHZ19B    0
#define ENABLE_MLX90640  0
#define ENABLE_INMP441   0

// --- Pines por defecto (ajústalos a tu cableado) -------------------------
#define I2C_SDA          21
#define I2C_SCL          22
// MH-Z19B por UART2:
#define MHZ19_RX_PIN     16   // RX del ESP32 <- TX del sensor
#define MHZ19_TX_PIN     17   // TX del ESP32 -> RX del sensor
// INMP441 por I2S:
#define I2S_SCK_PIN      14
#define I2S_WS_PIN       15
#define I2S_SD_PIN       32

// ===========================================================================
//  Objetos globales
// ===========================================================================
WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);
unsigned long lastPublish = 0;

#if ENABLE_BME280 || ENABLE_BH1750 || ENABLE_MLX90640
  #include <Wire.h>
#endif
#if ENABLE_BME280
  #include <Adafruit_BME280.h>
  Adafruit_BME280 bme;
  bool bmeOk = false;
#endif
#if ENABLE_BH1750
  #include <BH1750.h>
  BH1750 lightMeter;
  bool bhOk = false;
#endif
#if ENABLE_MHZ19B
  #include <MHZ19.h>
  MHZ19 mhz19;
  HardwareSerial mhzSerial(2);
#endif
#if ENABLE_MLX90640
  #include <Adafruit_MLX90640.h>
  Adafruit_MLX90640 mlx;
  float mlxFrame[32 * 24];
  bool mlxOk = false;
#endif
#if ENABLE_INMP441
  #include <driver/i2s.h>
#endif

// ===========================================================================
//  WiFi + MQTT
// ===========================================================================
void setupWiFi() {
  Serial.printf("Conectando a WiFi '%s' ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWiFi OK. IP: %s\n", WiFi.localIP().toString().c_str());
}

void reconnectMQTT() {
  while (!mqtt.connected()) {
    Serial.print("Conectando a MQTT... ");
    String clientId = String("esp32-") + AULA_ID;
    bool ok;
    if (strlen(MQTT_USER) > 0)
      ok = mqtt.connect(clientId.c_str(), MQTT_USER, MQTT_PASSWORD);
    else
      ok = mqtt.connect(clientId.c_str());

    if (ok) {
      Serial.println("conectado.");
    } else {
      Serial.printf("fallo (rc=%d). Reintento en 3s.\n", mqtt.state());
      delay(3000);
    }
  }
}

// Publica un objeto JSON en gemelo/<aula>/<sensor>.
void publishReading(const char* sensor, JsonDocument& metrics) {
  StaticJsonDocument<512> doc;
  doc["aula"]   = AULA_ID;
  doc["sensor"] = sensor;
  doc["ts"]     = (double) time(nullptr);   // epoch en segundos (si hay NTP)
  doc["metrics"] = metrics;

  char buffer[512];
  size_t n = serializeJson(doc, buffer);

  char topic[96];
  snprintf(topic, sizeof(topic), "%s/%s/%s", BASE_TOPIC, AULA_ID, sensor);
  mqtt.publish(topic, buffer, n);
  Serial.printf("-> %s  %s\n", topic, buffer);
}

// ===========================================================================
//  Lectura de cada sensor
// ===========================================================================
#if ENABLE_BME280
void readBME280() {
  if (!bmeOk) return;
  StaticJsonDocument<128> m;
  m["temp_c"]   = bme.readTemperature();
  m["hum_pct"]  = bme.readHumidity();
  m["pres_hpa"] = bme.readPressure() / 100.0F;
  publishReading("bme280", m);
}
#endif

#if ENABLE_BH1750
void readBH1750() {
  if (!bhOk) return;
  StaticJsonDocument<64> m;
  m["lux"] = lightMeter.readLightLevel();
  publishReading("bh1750", m);
}
#endif

#if ENABLE_MHZ19B
void readMHZ19B() {
  int co2 = mhz19.getCO2();
  if (co2 <= 0) return;               // lectura inválida
  StaticJsonDocument<64> m;
  m["co2_ppm"] = co2;
  publishReading("mhz19b", m);
}
#endif

#if ENABLE_MLX90640
void readMLX90640() {
  if (!mlxOk) return;
  if (mlx.getFrame(mlxFrame) != 0) return;

  float mn = mlxFrame[0], mx = mlxFrame[0], sum = 0;
  int occupied = 0;
  const float OCC_THRESHOLD_C = 28.0;   // pixel "caliente" ~ presencia humana
  for (int i = 0; i < 32 * 24; i++) {
    float t = mlxFrame[i];
    if (t < mn) mn = t;
    if (t > mx) mx = t;
    sum += t;
    if (t > OCC_THRESHOLD_C) occupied++;
  }
  StaticJsonDocument<128> m;
  m["min_c"]  = mn;
  m["max_c"]  = mx;
  m["mean_c"] = sum / (32 * 24);
  // Estimación tosca: agrupa pixeles calientes en "personas" (~15 px c/u).
  m["occupancy_est"] = occupied / 15;
  publishReading("mlx90640", m);
}
#endif

#if ENABLE_INMP441
// Calcula el nivel de presión sonora (aprox) a partir del RMS del audio I2S.
void readINMP441() {
  const int N = 512;
  int32_t samples[N];
  size_t bytesRead = 0;
  i2s_read(I2S_NUM_0, samples, sizeof(samples), &bytesRead, portMAX_DELAY);
  int n = bytesRead / sizeof(int32_t);
  if (n == 0) return;

  double sumSq = 0;
  for (int i = 0; i < n; i++) {
    // INMP441 entrega 24 bits alineados a la izquierda en 32 bits.
    double s = (double)(samples[i] >> 8);
    sumSq += s * s;
  }
  double rms = sqrt(sumSq / n);
  // dB relativo (referencia empírica). Calíbralo con un sonómetro real.
  double db = 20.0 * log10(rms + 1e-6) - 40.0;

  StaticJsonDocument<64> m;
  m["spl_db"] = db;
  publishReading("inmp441", m);
}
#endif

// Estado del propio ESP32 (no es un sensor: topic gemelo/<aula>/esp32).
void publishHeartbeat() {
  StaticJsonDocument<64> m;
  m["rssi"]       = WiFi.RSSI();
  m["uptime_s"]   = millis() / 1000;
  publishReading("esp32", m);
}

// ===========================================================================
//  setup / loop
// ===========================================================================
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n== Gemelo digital de aulas :: ESP32 ==");

  setupWiFi();

  // Hora por NTP (para timestamps correctos; si falla, el servidor usa su hora)
  configTime(0, 0, "pool.ntp.org", "time.google.com");

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);

#if ENABLE_BME280 || ENABLE_BH1750 || ENABLE_MLX90640
  Wire.begin(I2C_SDA, I2C_SCL);
#endif
#if ENABLE_BME280
  bmeOk = bme.begin(0x76) || bme.begin(0x77);
  Serial.printf("BME280: %s\n", bmeOk ? "OK" : "NO DETECTADO");
#endif
#if ENABLE_BH1750
  bhOk = lightMeter.begin();
  Serial.printf("BH1750: %s\n", bhOk ? "OK" : "NO DETECTADO");
#endif
#if ENABLE_MHZ19B
  mhzSerial.begin(9600, SERIAL_8N1, MHZ19_RX_PIN, MHZ19_TX_PIN);
  mhz19.begin(mhzSerial);
  mhz19.autoCalibration();
  Serial.println("MH-Z19B: inicializado (calentamiento ~3 min).");
#endif
#if ENABLE_MLX90640
  mlxOk = mlx.begin(MLX90640_I2CADDR_DEFAULT, &Wire);
  if (mlxOk) mlx.setRefreshRate(MLX90640_2_HZ);
  Serial.printf("MLX90640: %s\n", mlxOk ? "OK" : "NO DETECTADO");
#endif
#if ENABLE_INMP441
  i2s_config_t cfg = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = 16000,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = 0,
    .dma_buf_count = 4,
    .dma_buf_len = 512,
  };
  i2s_pin_config_t pins = {
    .bck_io_num = I2S_SCK_PIN,
    .ws_io_num = I2S_WS_PIN,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD_PIN,
  };
  i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL);
  i2s_set_pin(I2S_NUM_0, &pins);
  Serial.println("INMP441: I2S inicializado.");
#endif
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) setupWiFi();
  if (!mqtt.connected()) reconnectMQTT();
  mqtt.loop();

  if (millis() - lastPublish >= PUBLISH_PERIOD_MS) {
    lastPublish = millis();

#if ENABLE_BME280
    readBME280();
#endif
#if ENABLE_BH1750
    readBH1750();
#endif
#if ENABLE_MHZ19B
    readMHZ19B();
#endif
#if ENABLE_MLX90640
    readMLX90640();
#endif
#if ENABLE_INMP441
    readINMP441();
#endif
    publishHeartbeat();
  }
}
