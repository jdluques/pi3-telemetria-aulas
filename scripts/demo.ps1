# =============================================================================
#  demo.ps1  —  Demo del gemelo digital en Windows (sin hardware)
# -----------------------------------------------------------------------------
#  Levanta broker MQTT local + bridge + dashboard + simulador y abre el
#  navegador en el dashboard. No necesita Gaphor ni compilar nada (solo Python,
#  que instala uv).
#
#  Uso (recomendado): doble clic en  scripts\demo.bat
#  O en PowerShell:   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
#
#  Para DETENER: cierra esta ventana o pulsa Ctrl-C.
# =============================================================================
$ErrorActionPreference = "Stop"

# Carpeta del proyecto (este script está en project\scripts\).
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location (Join-Path $Root "server")

# --- 1. Asegurar uv ----------------------------------------------------------
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "[demo] Instalando uv..."
  powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "[demo] No se encontro 'uv'. Cierra y reabre PowerShell y reintenta."
  exit 1
}

# --- 2. Dependencias + configuración -----------------------------------------
Write-Host "[demo] Instalando dependencias (la primera vez tarda un poco)..."
uv sync

if (-not (Test-Path "config.yaml")) {
  Copy-Item "config.example.yaml" "config.yaml"
  Write-Host "[demo] Creado config.yaml a partir del ejemplo."
}

Write-Host "[demo] Generando el modelo de Gaphor (si no existe)..."
uv run gemelo -c config.yaml init-model 2>$null   # no falla si ya existe

# --- 3. Arrancar broker + bridge + dashboard en segundo plano ----------------
$procs = @()
function Stop-All {
  Write-Host "`n[demo] Deteniendo todo..."
  foreach ($p in $procs) { try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {} }
}

Write-Host "[demo] Iniciando broker MQTT local..."
$procs += Start-Process uv -ArgumentList "run","python","tools/broker_local.py" -PassThru
Start-Sleep -Seconds 2

Write-Host "[demo] Iniciando bridge..."
$procs += Start-Process uv -ArgumentList "run","gemelo","-c","config.yaml","run" -PassThru

Write-Host "[demo] Iniciando dashboard en http://localhost:8080 ..."
$procs += Start-Process uv -ArgumentList "run","gemelo","-c","config.yaml","dashboard","--host","127.0.0.1","--port","8080" -PassThru
Start-Sleep -Seconds 2

# --- 4. Abrir el navegador ---------------------------------------------------
Start-Process "http://localhost:8080"

# --- 5. Simulador en primer plano (Ctrl-C detiene la demo) -------------------
Write-Host ""
Write-Host "[demo] Todo listo. Dashboard: http://localhost:8080"
Write-Host "[demo] Publicando datos simulados. Pulsa Ctrl-C o cierra la ventana para detener."
Write-Host ""
try {
  uv run gemelo -c config.yaml simulate
} finally {
  Stop-All
}
