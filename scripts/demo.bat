@echo off
REM ===========================================================================
REM  demo.bat  -  Doble clic para lanzar la demo en Windows.
REM  Ejecuta demo.ps1 saltando la politica de ejecucion de PowerShell.
REM ===========================================================================
powershell -ExecutionPolicy Bypass -File "%~dp0demo.ps1"
echo.
echo Demo finalizada. Pulsa una tecla para cerrar.
pause >nul
