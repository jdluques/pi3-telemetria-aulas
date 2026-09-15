#!/usr/bin/env bash
# =============================================================================
#  demo.sh  —  Demo del gemelo digital en Linux y macOS (sin hardware)
# -----------------------------------------------------------------------------
#  Levanta TODO con un comando: broker MQTT local + bridge + dashboard +
#  simulador de sensores, y abre el navegador en el dashboard.
#
#  Uso:   bash scripts/demo.sh
#         (o:  ./scripts/demo.sh   si le das permiso de ejecución)
#
#  No necesita Gaphor ni compilar nada: solo Python (lo instala uv).
#  Para DETENER todo: pulsa Ctrl-C.
# =============================================================================
set -euo pipefail

# Carpeta del proyecto (este script está en project/scripts/).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/server"

# --- 1. Asegurar uv (gestor de Python) ---------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "[demo] uv no está instalado. Instalándolo..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # uv se instala normalmente en ~/.local/bin
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "[demo] No se encontró 'uv' tras instalarlo. Cierra y reabre la terminal"
  echo "       y vuelve a ejecutar este script."
  exit 1
fi

# --- 2. Dependencias + configuración -----------------------------------------
echo "[demo] Instalando dependencias (la primera vez tarda un poco)..."
uv sync

if [ ! -f config.yaml ]; then
  cp config.example.yaml config.yaml
  echo "[demo] Creado config.yaml a partir del ejemplo."
fi

echo "[demo] Generando el modelo de Gaphor (si no existe)..."
uv run gemelo -c config.yaml init-model || true   # no falla si ya existe

# --- 3. Arrancar broker + bridge + dashboard en segundo plano ----------------
PIDS=()
cleanup() {
  echo ""
  echo "[demo] Deteniendo todo..."
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  # Respaldo por si uv dejó procesos hijos:
  pkill -f "tools/broker_local.py" 2>/dev/null || true
  pkill -f "gemelo -c config.yaml" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[demo] Iniciando broker MQTT local..."
uv run python tools/broker_local.py & PIDS+=($!)
sleep 2

echo "[demo] Iniciando bridge..."
uv run gemelo -c config.yaml run & PIDS+=($!)

echo "[demo] Iniciando dashboard en http://localhost:8080 ..."
uv run gemelo -c config.yaml dashboard --host 127.0.0.1 --port 8080 & PIDS+=($!)
sleep 2

# --- 4. Abrir el navegador ---------------------------------------------------
URL="http://localhost:8080"
if command -v open >/dev/null 2>&1; then open "$URL" || true          # macOS
elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" || true # Linux
else echo "[demo] Abre manualmente: $URL"; fi

# --- 5. Simulador (en primer plano; Ctrl-C detiene la demo) ------------------
echo ""
echo "[demo] Todo listo. Dashboard: $URL"
echo "[demo] Publicando datos simulados. Pulsa Ctrl-C para detener TODO."
echo ""
uv run gemelo -c config.yaml simulate
