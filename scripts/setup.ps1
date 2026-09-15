# =============================================================================
#  setup.ps1  —  Solo INSTALAR (Windows), sin arrancar la demo.
# =============================================================================
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location (Join-Path $Root "server")

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "[setup] Instalando uv..."
  powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

uv sync
if (-not (Test-Path "config.yaml")) { Copy-Item "config.example.yaml" "config.yaml" }
uv run gemelo -c config.yaml init-model 2>$null

Write-Host ""
Write-Host "[setup] Listo. Para arrancar la demo: scripts\demo.bat (doble clic)"
