#!/usr/bin/env bash
# VerificaNoticias en Linux, macOS o GitHub Codespaces.
# Instala lo que falte (la primera vez tarda unos minutos) y abre la aplicación.
#   bash iniciar.sh                 instala si hace falta y abre la aplicación
#   bash iniciar.sh --solo-instalar instala y descarga los datos, sin abrirla
set -euo pipefail
cd "$(dirname "$0")"

buscar_uv() {
  if command -v uv >/dev/null 2>&1; then command -v uv; return 0; fi
  if [ -x "$HOME/.local/bin/uv" ]; then echo "$HOME/.local/bin/uv"; return 0; fi
  if [ -x "$HOME/.cargo/bin/uv" ]; then echo "$HOME/.cargo/bin/uv"; return 0; fi
  return 1
}

if ! UV="$(buscar_uv)"; then
  echo "Instalando uv (la herramienta que instala Python y las librerías)..."
  if ! curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null; then
    python3 -m pip install --user --quiet uv
  fi
  UV="$(buscar_uv)" || { echo "ERROR: no se pudo instalar uv. Revisa la conexión a internet."; exit 1; }
fi

echo "Comprobando las librerías (la primera vez tarda unos minutos)..."
"$UV" sync --frozen --no-dev --quiet

PYTHON=".venv/bin/python"
if [ ! -f datos/claimreview.db ]; then
  echo "Descargando las listas de medios y la base de verificaciones (unos 200 MB, una sola vez)..."
  "$PYTHON" -m verificanoticias.actualizar || echo "Aviso: algunos datos no se pudieron descargar. Puedes reintentar con el botón «Actualizar datos»."
elif [ ! -f datos/listas_importadas/domain_quality.csv ]; then
  "$PYTHON" -m verificanoticias.actualizar --solo-listas || echo "Aviso: las listas públicas no se pudieron descargar."
fi

if [ "${1:-}" = "--solo-instalar" ]; then
  echo "Instalación terminada. Para abrir la aplicación: bash iniciar.sh"
  exit 0
fi
exec "$PYTHON" -m verificanoticias
