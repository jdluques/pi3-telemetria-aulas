#!/usr/bin/env bash
# =============================================================================
#  setup.sh  —  Solo INSTALAR (Linux/macOS), sin arrancar la demo.
#  Instala uv (si falta), las dependencias y crea config.yaml + el modelo.
# =============================================================================
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/server"

if ! command -v uv >/dev/null 2>&1; then
  echo "[setup] Instalando uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

uv sync
[ -f config.yaml ] || cp config.example.yaml config.yaml
uv run gemelo -c config.yaml init-model || true

echo ""
echo "[setup] Listo. Para arrancar la demo:  bash scripts/demo.sh"
