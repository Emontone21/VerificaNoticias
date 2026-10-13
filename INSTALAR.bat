@echo off
setlocal
cd /d "%~dp0"
title Instalando VerificaNoticias
REM Todo se instala dentro de esta carpeta. Para desinstalar, basta con borrarla.
set "APP=%~dp0"
set "UV_INSTALL_DIR=%APP%herramientas\uv"
set "UV_NO_MODIFY_PATH=1"
set "UV_PYTHON_INSTALL_DIR=%APP%herramientas\python"
set "UV_PYTHON_PREFERENCE=only-managed"
set "UV_CACHE_DIR=%APP%herramientas\cache"
set "PYTHONUTF8=1"

echo.
echo  ==========================================================
echo    Instalando VerificaNoticias
echo    Necesita internet. La primera vez puede tardar 5 a 15 minutos.
echo  ==========================================================
echo.

call :buscar_uv
if defined UV goto tiene_uv
echo [1/4] Descargando el instalador uv...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
call :buscar_uv
if defined UV goto tiene_uv
echo.
echo  ERROR: no se pudo descargar el instalador uv.
echo  Revisa tu conexion a internet y vuelve a ejecutar INSTALAR.bat.
echo  Si el problema sigue, lee la seccion "Problemas frecuentes" del README.
goto error

:tiene_uv
echo [2/4] Instalando Python y las librerias necesarias...
"%UV%" sync --frozen --no-dev
if errorlevel 1 goto error_librerias

echo.
echo [3/4] Descargando las listas publicas de medios...
"%APP%.venv\Scripts\python.exe" -m verificanoticias.actualizar --solo-listas
if errorlevel 1 echo  Aviso: algunas listas no se pudieron descargar. Puedes reintentarlo luego con ACTUALIZAR_DATOS.bat

echo.
echo [4/4] Base de verificaciones de chequeadores, unos 200 MB de descarga.
echo       Tambien se puede descargar despues, desde la aplicacion.
choice /C SN /M "Descargarla ahora"
if errorlevel 2 goto fin
"%APP%.venv\Scripts\python.exe" -m verificanoticias.actualizar
if errorlevel 1 echo  Aviso: la base no se pudo descargar ahora. Puedes reintentarlo con el boton "Actualizar datos".

:fin
echo.
echo  ==========================================================
echo    Instalacion terminada.
echo    Para abrir la aplicacion, haz doble clic en INICIAR.bat
echo  ==========================================================
echo.
pause
exit /b 0

:error_librerias
echo.
echo  ERROR: no se pudieron instalar las librerias.
echo  Revisa tu conexion a internet y vuelve a ejecutar INSTALAR.bat.
goto error

:error
echo.
pause
exit /b 1

:buscar_uv
set "UV="
if exist "%UV_INSTALL_DIR%\uv.exe" set "UV=%UV_INSTALL_DIR%\uv.exe"
if exist "%UV_INSTALL_DIR%\bin\uv.exe" set "UV=%UV_INSTALL_DIR%\bin\uv.exe"
exit /b 0
