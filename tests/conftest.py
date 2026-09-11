"""Configuración común de los tests: hace importable el paquete 'gemelo'."""

import sys
from pathlib import Path

# El paquete vive en  server/gemelo. Lo agregamos al path para poder
# hacer 'import gemelo' desde los tests sin instalar nada.
SERVER = Path(__file__).resolve().parent.parent / "server"
sys.path.insert(0, str(SERVER))
