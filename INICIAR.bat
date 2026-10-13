@echo off
setlocal
cd /d "%~dp0"
title VerificaNoticias - no cierres esta ventana mientras uses la aplicacion
set "APP=%~dp0"
set "UV_INSTALL_DIR=%APP%herramientas\uv"
set "UV_NO_MODIFY_PATH=1"
set "UV_PYTHON_INSTALL_DIR=%APP%herramientas\python"
set "UV_PYTHON_PREFERENCE=only-managed"
set "UV_CACHE_DIR=%APP%herramientas\cache"
set "PYTHONUTF8=1"

if exist "%APP%.venv\Scripts\python.exe" goto arrancar
echo.
echo  La aplicacion todavia no esta instalada.
echo  Primero haz doble clic en INSTALAR.bat
echo.
pause
exit /b 1

:arrancar
"%APP%.venv\Scripts\python.exe" -m verificanoticias
if errorlevel 1 pause
