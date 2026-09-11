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
 │ BH1750   │─I2C─▶│  ESP32    │  WiFi  │  Mosquitto │       │           │      │──────▶│  Blocks con Notas │
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
   - escribe el último valor de cada sensor en la **Nota** de su bloque en el
     `.gaphor`, y
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

- **Python 3.12–3.14** y **[uv](https://docs.astral.sh/uv/)** (gestor de
  entornos y dependencias; instalación abajo).
- Un **broker MQTT** (Mosquitto) en la laptop que hará de servidor.
- **Gaphor** (se instala automáticamente con las dependencias).
- Opcional: los **ESP32 + sensores**. Sin hardware puedes probar todo con el
  **simulador** incluido.

Guía de instalación detallada, paso a paso y para cualquier carrera:
**[docs/GUIA_DE_USO.md](docs/GUIA_DE_USO.md)**.

---

## Inicio rápido

```bash
# 0. Instalar uv (una sola vez). En Linux/macOS:
#    curl -LsSf https://astral.sh/uv/install.sh | sh
#    En Windows (PowerShell):
#    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 1. Instalar dependencias (uv crea el entorno solo, a partir de pyproject.toml)
cd server
uv sync

# 2. Crear tu configuración
cp config.example.yaml config.yaml       # ajusta mqtt.host si hace falta

# 3. Generar un modelo de Gaphor de arranque
uv run gemelo -c config.yaml init-model

# 4. Arrancar el bridge (necesita un broker MQTT corriendo; ver la guía)
uv run gemelo -c config.yaml run

# 5. Sin hardware todavía: en otra terminal, simular sensores
uv run gemelo -c config.yaml simulate

# 6. Dashboard web en vivo (otra terminal): http://localhost:8080
uv run gemelo -c config.yaml dashboard
```

Después abre `model/gemelo_aulas.gaphor` con **Gaphor** para ver las Notas de
cada bloque, y/o el **dashboard** en el navegador para el estado en vivo.

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
│   ├── GUIA_DE_USO.md            ← instalar y usar, paso a paso ⭐
│   ├── ARQUITECTURA.md           ← cómo funciona por dentro
│   ├── PROTOCOLO_MQTT.md         ← formato de topics y mensajes JSON
│   └── SENSORES.md               ← qué mide cada sensor
├── firmware/esp32/               ← código para el ESP32 (Arduino/PlatformIO)
│   ├── esp32_gemelo_digital.ino
│   ├── config.example.h
│   └── platformio.ini
├── server/                       ← el bridge + dashboard (Python)
│   ├── gemelo/                   ← paquete principal
│   ├── tools/simulate_esp32.py   ← simulador (probar sin hardware)
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
| [GUIA_DE_USO.md](docs/GUIA_DE_USO.md) | Instalar y correr todo, paso a paso (todas las carreras) |
| [ARQUITECTURA.md](docs/ARQUITECTURA.md) | Cómo funciona por dentro y por qué |
| [PROTOCOLO_MQTT.md](docs/PROTOCOLO_MQTT.md) | Contrato de topics y JSON entre ESP32 y servidor |
| [SENSORES.md](docs/SENSORES.md) | Qué mide cada sensor y en qué unidades |

## Pruebas

```bash
cd server
uv sync
uv run pytest ../tests -q
```
