# Arquitectura del gemelo digital

## Visión general

El sistema tiene cuatro capas independientes que se comunican por contratos
simples (MQTT + JSON, y el archivo `.gaphor`). Cada capa se puede probar por
separado.

```
┌────────────┐   I2C/I2S/UART   ┌──────────┐   WiFi/MQTT   ┌────────────┐   MQTT   ┌────────────────────┐
│  Sensores  │ ───────────────▶ │  ESP32   │ ────────────▶ │  Broker    │ ───────▶ │  Bridge (Python)   │
│  físicos   │                  │ (firmware│               │ Mosquitto  │          │                    │
└────────────┘                  │  Arduino)│               │ (local)    │          │  mqtt_ingest.py    │
                                └──────────┘               └────────────┘          │       │            │
                                                                                   │       ▼            │
                                                                                   │  storage.py        │
                                                                                   │  (SQLite: histórico)│
                                                                                   │       │            │
                                                                                   │       ▼ cada Ns    │
                                                                                   │  gaphor_sync.py    │
                                                                                   └────────┬───────────┘
                                                                                            │ API Python
                                                                                            ▼
                                                                                   ┌────────────────────┐
                                                                                   │  model/*.gaphor     │
                                                                                   │  (Blocks SysML con  │
                                                                                   │  values = medición) │
                                                                                   └────────────────────┘
```

## Por qué un "bridge" entre MQTT y Gaphor

Gaphor es una **herramienta de modelado** (UML/SysML/RAAML) escrita en Python.
No es un servidor de datos ni una base de datos: no "escucha" MQTT. Lo que sí
ofrece es una **API de Python** para abrir un modelo `.gaphor`, modificar sus
elementos y volver a guardarlo.

Por eso, el gemelo digital se separa en dos ideas:

- **Estructura (diseño):** el modelo SysML en Gaphor — las aulas y sus
  sensores como bloques (`Block`). Es estable y lo edita el equipo.
- **Estado (datos en vivo):** las mediciones. Se guardan en SQLite y se
  "proyectan" sobre el modelo como **value properties** de SysML dentro de cada
  bloque (compartimento *values*: `Temperatura: °C = 23.4`).

### Value properties (dentro del bloque)

Por defecto (`gaphor.display: values`) el bridge escribe cada métrica como una
*value property* SysML en el bloque del sensor: crea el elemento `Property`
(tipado con un `ValueType` por unidad y `aggregation="composite"`), su
`LiteralString` de valor por defecto, y activa `show_values` en el `BlockItem`.
Todo esto se hace **editando el XML del `.gaphor` con la biblioteca estándar de
Python** (`gaphor_xml.py`) — sin la librería de Gaphor, por lo que corre en
cualquier SO sin compilar. Es **idempotente**: reutiliza properties y ValueTypes
por nombre para no inflar el modelo en cada sync. Si el bloque lo dibujó un
alumno sin properties, se crean automáticamente (ver `docs/MODELO_GAPHOR.md`).
Se conserva un modo `note` como alternativa/compatibilidad.

Un test de *round-trip* carga cada `.gaphor` generado con la **librería real de
Gaphor** para garantizar que abre correctamente (red de seguridad ante cambios
del formato).

El bridge **conserva** cualquier texto que el equipo escriba manualmente por
encima del marcador `── Datos en vivo (gemelo digital) ──`; solo reemplaza la
sección de datos vivos.

## Componentes del bridge (`server/gemelo/`)

| Módulo | Responsabilidad |
|--------|-----------------|
| `models.py` | Catálogo de sensores (del Excel) + parseo/validación de payloads MQTT. Lógica pura. |
| `config.py` | Carga `config.yaml` + variables de entorno. |
| `storage.py` | SQLite thread-safe: guarda el histórico y responde "último valor". |
| `mqtt_ingest.py` | Cliente MQTT (paho); convierte mensajes en `Reading`. |
| `gaphor_xml.py` | **Escritor/editor del `.gaphor` en Python puro** (stdlib `xml.etree`, sin GTK): genera el modelo y crea/actualiza las value properties. Funciona en Win/mac/Linux sin compilar. |
| `gaphor_sync.py` | Delega en `gaphor_xml`; conserva un lector con la librería real de Gaphor solo para los tests de validación. |
| `model_builder.py` | Genera el `.gaphor` inicial (delega en `gaphor_xml`). |
| `bridge.py` | Orquesta: ingest → storage → sync periódico. |
| `cli.py` | Línea de comandos (`run`, `init-model`, `sync-once`, `simulate`, `latest`, `dashboard`). |
| `tools_simulate.py` | Publica datos falsos para probar sin hardware. |
| `dashboard.py` | Dashboard web en vivo (solo stdlib): lee SQLite y muestra el estado con medidores por umbral, auto-refresco cada 2 s. |
| `thresholds.py` | Umbrales por métrica (normal/advertencia/alerta) con defaults en código y sobreescritura por `config.yaml`. |

## Concurrencia

- El **callback de MQTT** corre en el hilo de red de paho e **inserta** en SQLite.
- Un **hilo temporizador** lee "últimos valores" y **escribe** el modelo cada
  `sync_interval` segundos.
- `Storage` protege la conexión SQLite con un `Lock` (`check_same_thread=False`).
- La escritura del `.gaphor` es **atómica** (archivo temporal + `os.replace`)
  para que un fallo a mitad no corrompa el modelo.

Se sincroniza cada N segundos (no en cada mensaje) porque el `.gaphor` es un
archivo XML: reescribirlo por cada lectura sería costoso e innecesario.

## Decisiones y límites

- **Fuente de verdad = SQLite.** Gaphor solo muestra la última foto. El análisis
  histórico (gráficas, promedios) se hace sobre la base de datos. El archivo
  `.sqlite3` persiste entre ejecuciones y acumula todo el histórico; no se
  versiona (`.gitignore`). El dashboard lo consume para los sparklines
  (`/api/latest`) y la gráfica histórica en grande (`/api/history`).
- **Gaphor no auto-recarga** un archivo cambiado externamente: para ver el
  estado nuevo se reabre/recarga el modelo. Es adecuado para revisiones
  periódicas del gemelo, no para animación en tiempo real. Para monitoreo
  **en vivo** existe el **dashboard web** (`dashboard.py`), que lee la misma
  SQLite y se refresca solo. Gaphor = vista de diseño/estructura; dashboard =
  vista operativa en tiempo real.
- **MLX90640**: el ESP32 no envía los 768 píxeles; envía magnitudes derivadas
  (mín/máx/media y ocupación estimada) para no saturar la red.
- **Escalabilidad**: añadir un aula = una entrada en `config.yaml` + regenerar
  el modelo. Añadir un sensor = una entrada en `models.py::SENSORS`.

## Flujo de datos de una medición (ejemplo)

1. ESP32 del Aula A publica en `gemelo/aula-A/bme280`:
   `{"aula":"aula-A","sensor":"bme280","ts":1725...,"metrics":{"temp_c":23.4,...}}`
2. `mqtt_ingest` valida y crea un `Reading`.
3. `storage.insert` guarda una fila por métrica.
4. A los ≤ `sync_interval` s, `gaphor_sync.sync` busca el bloque
   `"BME280 (Aula A)"`, escribe las value properties y guarda el `.gaphor`.
5. El equipo recarga el modelo en Gaphor y ve `Temperatura: 23.4 °C`.
