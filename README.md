# Gemelo Digital de Aulas — PI3

Este repositorio contiene el **software del gemelo digital de dos aulas**: el
código que toma las mediciones de los sensores IoT instalados en cada aula y
las lleva, en vivo, hasta dos vistas del gemelo:

- el **modelo en Gaphor** (la representación SysML de las aulas y sus sensores), y
- un **dashboard web** que muestra el estado actual y se refresca solo.

> Si llegaste desde el curso: aquí no se modela el gemelo (eso se hace en
> Gaphor), sino que se **conecta el hardware real con el modelo**. Este repo es
> el "puente" entre los sensores y la representación del gemelo.

```
   Sensores            ESP32              Broker MQTT           Servidor (este repo)        Vistas del gemelo
 ┌──────────┐      ┌───────────┐        ┌────────────┐       ┌──────────────────┐       ┌──────────────────┐
 │ BME280   │─I2C─▶│           │        │            │       │  MQTT  ─▶ SQLite │       │  Gapho (.gaphor) │
 │ BH1750   │─I2C─▶│  ESP32    │  WiFi  │  Mosquitto │       │           │      │──────▶│  Blocks c/ values │
 │ MH-Z19B  │─UART▶│  DevKit   │──────▶ │ (en la red │──────▶│           ▼      │       ├──────────────────┤
 │ MLX90640 │─I2C─▶│           │  MQTT  │  local)    │  MQTT │      gaphor_sync │──────▶│  Dashboard web    │
 │ INMP441  │─I2S─▶│           │        │            │       │      dashboard   │       │  (tiempo real)    │
 └──────────┘      └───────────┘        └────────────┘       └──────────────────┘       └──────────────────┘
```

---

## ¿Qué hace, en concreto?

Un **gemelo digital** tiene dos partes: la **estructura** (cómo es el sistema)
y el **estado** (cómo está ahora mismo).

1. La **estructura** vive en **Gaphor**: cada aula y cada sensor es un bloque
   (`Block`) de SysML en un archivo `.gaphor`.
2. El **estado** son las mediciones. Los **ESP32** leen los sensores y publican
   cada lectura por **WiFi** usando **MQTT** (un protocolo de mensajería ligero
   para IoT).
3. Un **broker MQTT** (Mosquitto) corriendo en una laptop recibe esos mensajes.
4. El programa de este repositorio —el **bridge**— se suscribe al broker,
   guarda todo en una base de datos **SQLite** (el histórico) y proyecta el
   estado sobre las dos vistas:
   - escribe el último valor de cada sensor **dentro de su bloque** en el
     `.gaphor`, como *value properties* de SysML (`Temperatura: °C = 23.4`), y
   - lo sirve en un **dashboard web** que se actualiza cada 2 segundos.

> **¿Por qué hace falta un "bridge"?** Gaphor es una herramienta de *modelado*:
> no recibe datos por sí misma. Ofrece una API de Python para abrir un
> `.gaphor`, modificar sus elementos y guardarlo — y eso es justo lo que hace
> este programa.
>
> **Sobre "en vivo":** Gaphor no recarga solo un archivo que cambia por debajo;
> para ver el estado nuevo se reabre el modelo. Por eso, para monitoreo
> continuo, se usa el **dashboard web** (sí se refresca solo). El histórico
> completo siempre queda en SQLite para análisis posterior.

---

## Lo que necesitas

- **Nada nativo ni compiladores.** Todo el sistema es **Python puro** y
  funciona en **Windows, macOS y Linux**; solo necesitas
  **[uv](https://docs.astral.sh/uv/)** (instala Python y las dependencias por ti).
- Opcional, solo para *ver* el modelo: la **app de escritorio de Gaphor**
  ([descargas oficiales](https://gaphor.org/download/), sin MSYS ni build tools).
- Opcional: los **ESP32 + sensores**. Sin hardware, pruebas todo con el
  **simulador** incluido.

Instalación detallada por sistema operativo (y errores comunes):
**[docs/INSTALACION.md](docs/INSTALACION.md)**. Guía de uso paso a paso:
**[docs/GUIA_DE_USO.md](docs/GUIA_DE_USO.md)**.

---

## Inicio rápido (un solo paso) ⭐

Levanta broker + bridge + dashboard + simulador y abre el navegador:

- **Windows:** doble clic en `scripts\demo.bat`
- **macOS / Linux:** `bash scripts/demo.sh`

La primera vez instala `uv` y las dependencias solo. Luego abre
**http://localhost:8080**. `Ctrl-C` (o cerrar la ventana) detiene todo.

<details>
<summary>¿Prefieres hacerlo manual, comando por comando?</summary>

```bash
cd server
uv sync                                   # Python puro, sin compilar nada
cp config.example.yaml config.yaml        # Windows: copy config.example.yaml config.yaml
uv run gemelo -c config.yaml init-model   # genera el modelo .gaphor (sin Gaphor)
uv run python tools/broker_local.py       # broker MQTT local (otra terminal)
uv run gemelo -c config.yaml run          # bridge (otra terminal)
uv run gemelo -c config.yaml dashboard    # dashboard -> http://localhost:8080
uv run gemelo -c config.yaml simulate     # datos simulados (otra terminal)
```
</details>

Después abre `model/gemelo_aulas.gaphor` con **Gaphor** para ver los valores
dentro de cada bloque, y/o el **dashboard** en el navegador para el estado en vivo.

> **Nota:** todos los comandos se ejecutan con `uv run gemelo ...` desde la
> carpeta `server/`. `uv run` usa el entorno del proyecto automáticamente; no
> hace falta "activar" nada.

### ¿El modelo `.gaphor` lo generas tú o el código?

Las dos formas funcionan. El bridge no depende de un modelo generado por la
herramienta: busca los bloques **por su nombre** para escribirles la Nota.

- `init-model` crea una **plantilla de arranque** (opcional) con los 12 bloques
  y los nombres ya correctos, para no dibujarlos a mano.
- También puedes usar **tu propio `.gaphor`** dibujado en Gaphor: solo apunta
  `model_path` (en `config.yaml`) a tu archivo y haz que los nombres de los
  bloques coincidan (o mapéalos en `config.yaml → naming.overrides`).

Recomendado: empezar con `init-model` y luego personalizar el diagrama en
Gaphor (mover, agrupar, añadir relaciones).

---

## Mapa del repositorio

```
project/
├── README.md                     ← este archivo
├── docs/                         ← documentación
│   ├── INSTALACION.md            ← instalar por SO (Win/mac/Linux) ⭐
│   ├── GUIA_DE_USO.md            ← usar todo, paso a paso
│   ├── MODELO_GAPHOR.md          ← definir tu modelo / valores en el bloque
│   ├── ARQUITECTURA.md           ← cómo funciona por dentro
│   ├── PROTOCOLO_MQTT.md         ← formato de topics y mensajes JSON
│   └── SENSORES.md               ← qué mide cada sensor
├── scripts/                      ← demo de un clic (demo.sh / demo.bat)
├── firmware/esp32/               ← código para el ESP32 (Arduino/PlatformIO)
│   ├── esp32_gemelo_digital.ino
│   ├── config.example.h
│   └── platformio.ini
├── server/                       ← el bridge + dashboard (Python puro)
│   ├── gemelo/                   ← paquete principal (incl. gaphor_xml.py)
│   ├── tools/                    ← simulador + broker MQTT local
│   ├── config.example.yaml
│   ├── pyproject.toml            ← dependencias (uv)
│   └── uv.lock                   ← versiones exactas bloqueadas
├── model/                        ← aquí vive el .gaphor
└── tests/                        ← pruebas automáticas (pytest)
```

---

## Comandos disponibles

Desde `server/`, con `uv run gemelo -c config.yaml <comando>`:

| Comando | Qué hace |
|---------|----------|
| `run` | Arranca el bridge (uso normal): escucha MQTT y actualiza el modelo. |
| `dashboard` | Sirve el dashboard web en vivo (`http://localhost:8080`). |
| `init-model` | Genera el `.gaphor` de arranque. `--force` para regenerarlo. |
| `sync-once` | Vuelca las últimas mediciones al modelo una vez y termina. |
| `simulate` | Publica datos falsos por MQTT (probar sin hardware). |
| `latest` | Muestra en consola las últimas mediciones guardadas. |

---

## Documentación

| Documento | Para qué |
|-----------|----------|
| [INSTALACION.md](docs/INSTALACION.md) | Instalar en Windows / macOS / Linux (y errores comunes) |
| [GUIA_DE_USO.md](docs/GUIA_DE_USO.md) | Instalar y correr todo, paso a paso (todas las carreras) |
| [MODELO_GAPHOR.md](docs/MODELO_GAPHOR.md) | Definir tu propio modelo y cómo los datos aparecen dentro del bloque |
| [ARQUITECTURA.md](docs/ARQUITECTURA.md) | Cómo funciona por dentro y por qué |
| [PROTOCOLO_MQTT.md](docs/PROTOCOLO_MQTT.md) | Contrato de topics y JSON entre ESP32 y servidor |
| [SENSORES.md](docs/SENSORES.md) | Qué mide cada sensor y en qué unidades |

## Pruebas

```bash
cd server
uv sync
uv run pytest ../tests -q                 # núcleo (los tests que usan Gaphor se saltan)

# Suite completa, incluyendo la validación round-trip contra Gaphor real
# (requiere el extra 'gaphor'; fácil en Linux):
uv sync --extra gaphor
uv run pytest ../tests -q
```
