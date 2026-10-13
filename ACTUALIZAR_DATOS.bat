@echo off
setlocal
cd /d "%~dp0"
title Actualizando datos de VerificaNoticias
set "APP=%~dp0"
set "UV_INSTALL_DIR=%APP%herramientas\uv"
set "UV_NO_MODIFY_PATH=1"
set "UV_PYTHON_INSTALL_DIR=%APP%herramientas\python"
set "UV_PYTHON_PREFERENCE=only-managed"
set "UV_CACHE_DIR=%APP%herramientas\cache"
set "PYTHONUTF8=1"

if exist "%APP%.venv\Scripts\python.exe" goto actualizar
echo  La aplicacion todavia no esta instalada. Primero haz doble clic en INSTALAR.bat
pause
exit /b 1

:actualizar
"%APP%.venv\Scripts\python.exe" -m verificanoticias.actualizar
echo.
pause
