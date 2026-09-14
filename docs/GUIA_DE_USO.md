# Guía de uso — paso a paso (para todos los equipos)

Esta guía está pensada para que **cualquier persona**, sin importar su carrera,
pueda poner a funcionar el gemelo digital. Si algo no funciona, revisa la
sección [Problemas comunes](#problemas-comunes) al final.

> **Idea en una frase:** los sensores mandan datos por WiFi a un programa
> (el *bridge*) en una laptop; ese programa los mete al modelo de Gaphor.

Hay **dos formas de probarlo**:
- **Modo simulación (sin hardware):** ideal para empezar y para equipos que no
  tocan el ESP32. Un programa "finge" ser los sensores. → [Parte B](#parte-b--probar-sin-hardware-simulador)
- **Modo real (con ESP32 y sensores):** → [Parte D](#parte-d--con-el-esp32-real)

---

## ⚡ Ruta más rápida (ver el dashboard en 5 minutos, sin hardware)

Si solo quieres **ver el gemelo funcionando ya**, copia y pega esto. Necesitas
tener **uv** instalado (ver [A.1](#a1-uv-gestor-de-python-y-dependencias)); no
hace falta ni Mosquitto ni el ESP32.

**Preparación (una sola vez):**
```bash
cd server
uv sync                              # instala todo (tarda un poco la 1ª vez)
cp config.example.yaml config.yaml   # Windows: copy config.example.yaml config.yaml
uv run gemelo -c config.yaml init-model   # crea el modelo de Gaphor
```

Ahora abre **4 terminales**, todas dentro de la carpeta `server/`:

| Terminal | Comando | Qué hace |
|----------|---------|----------|
| **1 · Broker** | `uv run python tools/broker_local.py` | Broker MQTT local (reemplaza a Mosquitto para la demo). Debe decir *"MQTT local escuchando en 0.0.0.0:1883"*. |
| **2 · Bridge** | `uv run gemelo -c config.yaml run` | Recibe los datos y actualiza el gemelo. Debe decir *"Conectado al broker"* y *"Bridge en marcha"*. |
| **3 · Dashboard** | `uv run gemelo -c config.yaml dashboard` | Sirve la web. Abre **<http://localhost:8080>** en el navegador. |
| **4 · Simulador** | `uv run gemelo -c config.yaml simulate` | "Finge" los sensores publicando datos cada 3 s. |

En cuanto arranque el simulador (Terminal 4), el **dashboard** (Terminal 3) se
llenará solo con las dos aulas y sus sensores, y se irá refrescando cada 2 s.
Para detener todo, `Ctrl-C` en cada terminal.

> El orden importa: primero el **broker** (T1), luego **bridge** (T2) y
> **dashboard** (T3), y al final el **simulador** (T4).

¿Quieres el detalle de cada paso, ver los datos también dentro de Gaphor, o
conectar el ESP32 real? Sigue leyendo.

---

## Parte A — Preparar la laptop (una sola vez)

Necesitas **tres cosas** en la laptop que hará de servidor: **uv**, el
**broker MQTT** y el **código** de este proyecto.

### A.1 uv (gestor de Python y dependencias)

Usamos [uv](https://docs.astral.sh/uv/): instala Python y todas las
dependencias por ti, sin pelear con entornos virtuales a mano.

- **Linux/macOS:**
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows (PowerShell):**
  ```powershell
  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

Cierra y reabre la terminal, y verifica:
```bash
uv --version
```

> No necesitas instalar Python aparte: si te falta una versión compatible
> (3.12–3.14), `uv` la descarga sola al ejecutar `uv sync`.

### A.2 El broker MQTT (Mosquitto)

El broker es el "cartero" que recibe los mensajes de los sensores y los reparte.

- **Windows:** descarga el instalador de <https://mosquitto.org/download/> e
  instálalo. Se instala como servicio y arranca solo.
- **macOS:** `brew install mosquitto` y luego `brew services start mosquitto`.
- **Linux (Debian/Ubuntu):**
  ```bash
  sudo apt install mosquitto mosquitto-clients
  sudo systemctl enable --now mosquitto
  ```

Por defecto Mosquitto escucha en el puerto **1883** y acepta conexiones sin
contraseña en la red local. Eso nos sirve para el proyecto.

> **¿No puedes instalar Mosquitto?** Este repo incluye un **broker local en
> Python** (no requiere instalación aparte, ya viene con `uv sync`):
> ```bash
> cd server
> uv run python tools/broker_local.py
> ```
> Sirve para la demo y para pruebas en una sola laptop. Para uso real con
> varias máquinas/ESP32 en la red, se recomienda Mosquitto.

> **Para que el ESP32 pueda conectarse desde otra máquina**, Mosquitto debe
> aceptar conexiones externas. Crea un archivo de configuración (p. ej.
> `mosquitto.conf`) con:
> ```
> listener 1883 0.0.0.0
> allow_anonymous true
> ```
> y arráncalo con `mosquitto -c mosquitto.conf -v`. En modo simulación esto
> no hace falta (todo corre en la misma laptop).

### A.3 El código de este proyecto y sus dependencias

```bash
# Colócate en la carpeta del proyecto (donde está este README) y luego:
cd server
uv sync
```

`uv sync` lee `pyproject.toml` / `uv.lock`, crea el entorno y instala todo: el
bridge, el cliente MQTT, **Gaphor** (la herramienta de modelado) y las
herramientas de prueba. La primera vez tarda un poco (descarga Gaphor).

---

## Parte B — Probar sin hardware (simulador)

Versión detallada de la ruta rápida de arriba. Usarás varias terminales, todas
dentro de `server/`.

> **Antes de empezar:** debe haber un **broker MQTT corriendo** (Mosquitto de
> [A.2](#a2-el-broker-mqtt-mosquitto), o el broker local:
> `uv run python tools/broker_local.py`). El bridge no arranca sin broker.

### B.1 Configuración

```bash
cd server
cp config.example.yaml config.yaml      # en Windows PowerShell: copy config.example.yaml config.yaml
```
Como todo corre en la misma laptop, no hace falta editar nada (el broker es
`localhost`).

### B.2 Generar el modelo de Gaphor

```bash
uv run gemelo -c config.yaml init-model
```
Esto crea `../model/gemelo_aulas.gaphor` con un bloque por cada sensor de cada
aula. Verás un mensaje `[ok] Modelo generado en: ...`.

> **¿Ya tienen su propio `.gaphor`?** No hace falta usar `init-model`: pueden
> apuntar `model_path` (en `config.yaml`) a su modelo. El bridge solo necesita
> que los **nombres de los bloques** coincidan con `"<Modelo> (<Aula>)"`
> (p. ej. `BME280 (Aula A)`) o que los mapeen en `naming.overrides`.

### B.3 Arrancar el bridge (Terminal 1)

```bash
uv run gemelo -c config.yaml run
```
Debe decir `Conectado al broker; suscrito a gemelo/#` y `Bridge en marcha`.

### B.4 Arrancar el simulador (Terminal 2)

```bash
cd server
uv run gemelo -c config.yaml simulate
```
Empezará a publicar datos. En la Terminal 1 verás llegar las lecturas y, cada
10 segundos, `Modelo actualizado: ...`.

### B.5 Ver los datos en Gaphor (Terminal 3 o el menú de apps)

```bash
# desde server/ (usa el Gaphor instalado por uv):
uv run gaphor ../model/gemelo_aulas.gaphor
```
> Si instalaste Gaphor aparte (app de escritorio), también puedes abrir el
> archivo `model/gemelo_aulas.gaphor` con doble clic.

En Gaphor:
1. Abre el diagrama **"Gemelo Digital - Aulas"** (doble clic en el árbol de la izquierda).
2. Mira el bloque de un sensor, p. ej. **"BME280 (Aula A)"**: la medición actual
   aparece **dentro del bloque**, en el compartimento *values*
   (`Temperatura: °C = 23.4`, `Humedad relativa: % = 55`, …), más `Actualizado`
   con la hora. La sección **Note** del panel derecho guarda la descripción del sensor.
3. Para ver valores nuevos, **cierra y reabre** el modelo (o vuelve a abrir el
   archivo): Gaphor no recarga solo mientras el bridge escribe por debajo.

> ¿Quieres tu propio diagrama con otros nombres? El bridge crea y rellena esas
> value properties solo; tú solo aseguras el nombre del bloque. Ver
> **[MODELO_GAPHOR.md](MODELO_GAPHOR.md)**.

> ¿Solo quieres una foto puntual sin dejar el bridge corriendo? Usa
> `uv run gemelo -c config.yaml sync-once` y luego abre Gaphor.

También puedes ver los últimos valores en texto, sin Gaphor:
```bash
uv run gemelo -c config.yaml latest
```

### B.6 Dashboard web en vivo (recomendado) 🖥️

Para ver el gemelo **actualizándose solo** (Gaphor no lo hace), levanta el
dashboard en otra terminal:

```bash
cd server
uv run gemelo -c config.yaml dashboard
```

Abre en el navegador **<http://localhost:8080>**. Verás las dos aulas con cada
sensor y su valor actual, con colores de estado:

- 🟢 **verde** = dentro de rango  🟡 **ámbar** = advertencia  🔴 **rojo** = alerta
- 🔵 **azul** = valor informativo (sin umbral)  ⚪ **gris** = sin datos
- Un sensor que deja de reportar >30 s se marca como **"sin señal"**.

Cada métrica con un "rango normal" (temperatura, humedad, CO₂, luz, ruido)
muestra además un **medidor**: una barra verde/ámbar/roja con un marcador que
indica dónde cae el valor actual. Las magnitudes sin rango claro (presión,
ocupación) se muestran solo como número.

Al lado del valor aparece un **sparkline**: una mini-gráfica con la **tendencia
reciente** (los últimos valores del histórico guardado en SQLite), para ver de
un vistazo si algo sube o baja. Toma el color del estado actual.

**Pasa el mouse sobre cualquier métrica** y se abre una **gráfica histórica en
grande** (más puntos, ejes, mín/máx/promedio y las bandas de color de fondo).
Mientras la miras, el refresco automático se pausa; al quitar el mouse, vuelve
al modo en vivo.

El eje horizontal va por **tiempo real**. Si apagaste el sistema un rato, ese
periodo sin datos aparece como un **hueco**: la línea se corta en vez de unir
con una recta engañosa los dos tramos (y las estadísticas muestran cuántos
huecos hay). Así distingues un apagón de una medición continua.

#### ¿Se guardan los datos permanentemente?

Sí. El bridge guarda **todas** las lecturas en la base de datos SQLite
(`db_path` del `config.yaml`, por defecto `server/gemelo.sqlite3`). Ese archivo
**persiste entre ejecuciones**: cada vez que corres el sistema se van
acumulando más datos, y de ahí salen los sparklines y la gráfica histórica.

- **No se sube a Git** (está en `.gitignore`, junto con sus archivos `-wal`/`-shm`).
- Para empezar de cero, simplemente borra el archivo `.sqlite3`.
- Para respaldarlo o analizarlo, cópialo: es una base SQLite estándar (puedes
  abrirlo con cualquier visor de SQLite o con `sqlite3`).

Se refresca solo cada 2 segundos. Puedes abrirlo también desde otro dispositivo
de la red (celular, otra laptop) usando `http://<IP-de-la-laptop>:8080`.

#### Ajustar qué es "normal" (umbrales)

Los umbrales tienen **valores por defecto sensatos en el código**
(`server/gemelo/thresholds.py`), así que funciona sin configurar nada. Si
quieres cambiarlos (p. ej. tu aula tolera hasta 1000 ppm de CO₂ en vez de
1200), agrégalo en `config.yaml` bajo `thresholds:` — solo cambia lo que
indiques, el resto conserva el default:

```yaml
thresholds:
  temp_c:
    ok_min: 20
    ok_max: 25
  co2_ppm:
    alert_max: 1000
```

Campos por métrica: `ok_min`/`ok_max` (rango verde), `alert_min`/`alert_max`
(fuera = rojo; entre medio = ámbar), `bar_min`/`bar_max` (escala de la barra).
Puedes incluso dar umbral a métricas que no lo traen (p. ej. `occupancy_est`).

---

## Parte C — Entender los comandos

Todos se ejecutan desde la carpeta `server/` con `uv run gemelo -c config.yaml <comando>`:

| Comando | Qué hace |
|---------|----------|
| `run` | Arranca el bridge (uso normal): escucha MQTT y actualiza Gaphor. |
| `init-model` | Genera el archivo `.gaphor` inicial. Usa `--force` para regenerarlo. |
| `sync-once` | Vuelca las últimas mediciones al modelo una sola vez y termina. |
| `simulate` | Publica datos falsos (para probar sin sensores). `--interval N`, `--count N`. |
| `latest` | Muestra en pantalla las últimas mediciones guardadas. |
| `dashboard` | Sirve el dashboard web en vivo. `--host`, `--port` (default 8080). |

---

## Parte C-bis — Usar tu propio diagrama de Gaphor (nombres distintos)

No es obligatorio usar el modelo que genera `init-model`. Cada grupo puede
dibujar **su propio diagrama** en Gaphor, con los nombres de bloque que quiera.
El bridge escribe la medición en el bloque **buscándolo por su nombre**, así que
solo hay que decirle qué nombre tiene cada sensor. Eso se hace en la sección
`naming` del `config.yaml`. También apunta `model_path` a tu archivo.

### Cómo arma el nombre el bridge

Para cada `(aula, sensor)` que llega por MQTT, calcula el nombre esperado con
estas piezas:

| Sensor (key en el topic MQTT) | `{model}` |
|-------------------------------|-----------|
| `inmp441`  | INMP441 |
| `mhz19b`   | MH-Z19B |
| `bme280`   | BME280 |
| `bh1750`   | BH1750 (GY-302) |
| `mlx90640` | MLX90640 32x24 |

Variables disponibles: `{model}`, `{aula_name}`, `{aula_id}`, `{sensor}`.

### Opción A — Nombres con un patrón → cambia `template`

Si todos tus bloques siguen el mismo patrón (p. ej. `204 · BME280`,
`204 · MH-Z19B`, …), basta ajustar la plantilla y los nombres de aula:

```yaml
model_path: ../model/mi_diagrama.gaphor

aulas:
  - id: aula-A
    name: "204"          # el nombre que usas en el diagrama
  - id: aula-B
    name: "205"

naming:
  template: "{aula_name} · {model}"   # -> "204 · BME280"
```

### Opción B — Nombres libres → usa `overrides`

Si cada bloque tiene un nombre arbitrario (sin patrón), mapéalos uno por uno.
El `override` gana sobre el `template`:

```yaml
naming:
  template: "{model} ({aula_name})"   # se usa solo cuando no hay override
  overrides:
    - aula: aula-A                     # id del aula (el del topic MQTT)
      sensor: mhz19b                   # key del sensor (tabla de arriba)
      element: "Sensor CO2 - Aula 204" # nombre EXACTO del bloque en Gaphor
    - aula: aula-A
      sensor: bme280
      element: "Ambiente T/H/P (204)"
    - aula: aula-B
      sensor: bme280
      element: "BME280 salón B"
```

### Detalles que importan

- **Nombre exacto:** debe coincidir tal cual (mayúsculas, espacios y acentos).
  En Gaphor, haz clic en el bloque y copia su nombre del árbol de modelo.
- **Nombres únicos:** cada bloque a actualizar debe tener nombre único en el
  modelo; si hay dos iguales, el bridge no sabe a cuál escribir.
- **Cómo saber si acertaste:** arranca el bridge y mira el log. Si un sensor no
  encuentra su bloque, avisa con el nombre que estaba buscando:
  ```
  Sensores sin bloque en el modelo (revisa nombres): Sensor CO2 - Aula 204
  ```
  Compara ese texto con el nombre real de tu bloque y ajusta `template` u
  `overrides` hasta que la lista quede vacía.

---

## Parte D — Con el ESP32 real

Esto lo hace el equipo encargado del hardware, pero cualquiera puede seguirlo.

### D.1 Instalar el entorno del ESP32

Opción sencilla: **IDE de Arduino** (<https://www.arduino.cc/en/software>).
1. Añade el soporte para ESP32: *Archivo → Preferencias → Gestor de URLs
   adicionales* y pega
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`.
   Luego *Herramientas → Placa → Gestor de tarjetas* → instala **esp32**.
2. Instala las librerías del *Library Manager* que aparecen listadas al inicio
   de `firmware/esp32/esp32_gemelo_digital.ino` (solo las de los sensores que
   vas a usar).

> Alternativa para quien lo prefiera: **PlatformIO** con el archivo
> `platformio.ini` que ya viene incluido.

### D.2 Configurar el firmware

1. En `firmware/esp32/`, copia `config.example.h` a `config.h`.
2. Edita `config.h`:
   - `WIFI_SSID` y `WIFI_PASSWORD`: tu red WiFi.
   - `MQTT_HOST`: la **IP de la laptop** donde corre Mosquitto (ver D.3).
   - `AULA_ID`: `"aula-A"` en un ESP32 y `"aula-B"` en el otro.
3. En el `.ino`, activa los sensores que tengas conectados poniendo su
   `#define ENABLE_XXX 1`. Empieza con uno solo (BME280 ya viene activo).

### D.3 Averiguar la IP de la laptop

En la laptop del broker, en una terminal:
- **Windows:** `ipconfig` → busca "Dirección IPv4" (algo como `192.168.1.100`).
- **macOS/Linux:** `ip addr` o `ifconfig` → busca la IP de tu WiFi.

El ESP32 y la laptop deben estar en la **misma red WiFi**.

### D.4 Subir y verificar

1. Conecta el ESP32 por USB, selecciona la placa **"ESP32 Dev Module"** y el
   puerto correcto, y sube el sketch.
2. Abre el *Monitor Serie* a **115200 baudios**. Deberías ver
   `WiFi OK`, `MQTT conectado` y líneas `-> gemelo/aula-A/bme280 {...}`.
3. En la laptop, arranca el bridge (`uv run gemelo -c config.yaml run`) y
   abre el modelo en Gaphor como en la Parte B.

Para comprobar que los mensajes llegan al broker, sin siquiera el bridge:
```bash
mosquitto_sub -h localhost -t "gemelo/#" -v
```

---

## Problemas comunes

| Síntoma | Causa probable / solución |
|---------|---------------------------|
| `Connection refused` al arrancar el bridge | Mosquitto no está corriendo. Arráncalo (ver A.2). |
| El ESP32 dice "Conectando a MQTT... fallo" | `MQTT_HOST` mal, o el broker no acepta conexiones externas (ver nota en A.2), o no están en la misma red. |
| El bridge dice `Sensores sin bloque en el modelo` | El nombre del bloque en Gaphor no coincide con el esperado. Regenera el modelo (`init-model --force`) o ajusta `naming` en `config.yaml`. |
| `No existe el modelo ...` | Falta generar el modelo: `uv run gemelo -c config.yaml init-model`. |
| Gaphor no muestra los valores nuevos | Es normal: recarga/reabre el modelo. Gaphor no auto-refresca. |
| `command not found: gaphor` o `gemelo` | Faltó `uv sync`, o no estás usando `uv run`. Ejecuta los comandos como `uv run gemelo ...` / `uv run gaphor ...` desde `server/`. |
| `uv: command not found` | Reinstala uv (Parte A.1) y reabre la terminal para que tome el PATH. |
| El ESP32 no compila | Desactiva (`ENABLE_XXX 0`) los sensores cuyas librerías aún no instalaste. |
| Lecturas de CO2 raras al inicio (MH-Z19B) | El sensor necesita ~3 min de calentamiento. Es normal. |

¿Sigue sin funcionar? Revisa [ARQUITECTURA.md](ARQUITECTURA.md) para entender
qué hace cada parte, y [PROTOCOLO_MQTT.md](PROTOCOLO_MQTT.md) para el formato
de los mensajes.
