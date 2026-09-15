# Instalación (Windows · macOS · Linux)

Objetivo: que **cualquiera** ponga a funcionar el gemelo con el **mínimo de
pasos**, sin importar el sistema operativo y **sin compilar nada**.

> **Lo importante:** el sistema (dashboard, bridge, simulador, broker y la
> generación/actualización del modelo `.gaphor`) es **Python puro**. Se instala
> con un solo comando y **no necesita GTK, MSYS2 ni "build tools"**. Lo único
> que se instala aparte —y solo si quieres *ver* el modelo— es la **app de
> escritorio de Gaphor** (un instalador normal).

---

## Opción A — Un solo paso (recomendada) ⭐

Descarga el proyecto (botón verde **Code → Download ZIP** en GitHub, o `git
clone`) y ejecuta el script de demo. Levanta todo (broker + bridge + dashboard +
simulador) y abre el navegador.

### Windows
1. Descomprime el proyecto.
2. Entra en la carpeta `scripts` y **haz doble clic en `demo.bat`**.
   - La primera vez instala `uv` y las dependencias solo (puede tardar 1–2 min).
   - Se abrirá el navegador en `http://localhost:8080`.
3. Para detener: cierra la ventana o pulsa `Ctrl-C`.

### macOS / Linux
```bash
bash scripts/demo.sh
```
(Instala `uv` si falta, prepara todo y abre el navegador. `Ctrl-C` detiene todo.)

> ¿Solo instalar sin arrancar la demo? Usa `scripts/setup.sh` (macOS/Linux) o
> `scripts\setup.ps1` (Windows).

---

## Opción B — Manual (si prefieres controlar cada paso)

1. **Instalar uv** (gestiona Python y dependencias; instala Python por ti):
   - **Windows (PowerShell):** `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - **macOS / Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`

   Cierra y reabre la terminal. Verifica: `uv --version`.

2. **Instalar dependencias** (Python puro, sin compilar nada):
   ```bash
   cd server
   uv sync
   cp config.example.yaml config.yaml     # Windows: copy config.example.yaml config.yaml
   ```

3. **Arrancar** (ver [GUIA_DE_USO.md](GUIA_DE_USO.md) para el detalle por terminal):
   ```bash
   uv run python tools/broker_local.py       # broker MQTT local
   uv run gemelo -c config.yaml run          # bridge
   uv run gemelo -c config.yaml dashboard    # dashboard -> http://localhost:8080
   uv run gemelo -c config.yaml simulate     # datos simulados
   ```

---

## Ver el modelo en Gaphor (opcional)

El dashboard web funciona sin instalar Gaphor. Para **abrir el modelo `.gaphor`**
(la vista SysML del gemelo) instala la **app de escritorio** desde la página
oficial — trae todo incluido, **sin MSYS ni build tools**:

- **Descargas oficiales:** <https://gaphor.org/download/> (Windows `.exe`,
  macOS `.dmg`, Linux Flatpak/AppImage).

El bridge **genera y actualiza** el `.gaphor` por su cuenta (con un backend XML
propio en Python puro), así que **no necesitas instalar Gaphor por pip**. Solo
abres el archivo con la app para verlo (recuerda **recargarlo** para ver valores
nuevos; el dashboard sí se refresca solo).

---

## Errores comunes y qué hacer

| Mensaje / síntoma | Causa y solución |
|-------------------|------------------|
| `uv: command not found` / `no se reconoce uv` | uv no quedó en el PATH. Cierra y reabre la terminal; si persiste, reinstala uv (Opción B, paso 1). |
| El script no arranca en Windows (política de ejecución) | Usa **`demo.bat`** (doble clic); ya salta la restricción. Evita ejecutar `demo.ps1` directamente. |
| `Connection refused` al arrancar el bridge | No hay broker. Arranca `tools/broker_local.py` (o Mosquitto). El script de demo ya lo hace por ti. |
| El navegador no abre solo | Abre manualmente `http://localhost:8080`. |
| Quiero instalar Gaphor por **pip** y falla (PyGObject/GTK, "build wheels", MSYS2, VS Build Tools) | **No hace falta.** Ese es justo el camino que evitamos: usa la **app de escritorio** (arriba) para ver el modelo. El proyecto NO requiere Gaphor por pip. |
| `No existe el modelo ...` | Genera el modelo: `uv run gemelo -c config.yaml init-model` (el script de demo ya lo hace). |

> Más problemas (ESP32, red, sensores) en [GUIA_DE_USO.md](GUIA_DE_USO.md#problemas-comunes).

---

## ¿Y para desarrollar/validar? (equipo CS)

Los tests que validan que el `.gaphor` generado abre en Gaphor real usan la
librería de Gaphor. Esa parte SÍ necesita el entorno nativo y se instala como
**extra opcional** (fácil en Linux):
```bash
cd server
uv sync --extra gaphor
uv run pytest ../tests -q
```
Sin ese extra, esos tests de round-trip se **saltan** y el resto pasa igual.
