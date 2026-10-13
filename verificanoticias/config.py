"""Carga de la configuración y rutas de la aplicación.

Los valores predeterminados están en ``config_predeterminada.yaml`` (dentro del
paquete). El usuario edita ``config.yaml`` en la carpeta principal; lo que
falte en ese archivo se completa con los valores predeterminados.
"""

from __future__ import annotations

import copy
import os
import shutil
import threading
from pathlib import Path
from typing import Any

import yaml

PAQUETE = Path(__file__).resolve().parent
RAIZ = PAQUETE.parent
ARCHIVO_PREDETERMINADO = PAQUETE / "config_predeterminada.yaml"

_lock = threading.Lock()
_config: dict | None = None


class ErrorConfig(Exception):
    """El archivo de configuración no se puede leer."""


def ruta_config_usuario() -> Path:
    return Path(os.environ.get("VERIFICANOTICIAS_CONFIG", RAIZ / "config.yaml"))


def ruta_datos() -> Path:
    """Carpeta donde se guardan caché, historial, índice e importaciones."""
    ruta = Path(os.environ.get("VERIFICANOTICIAS_DATOS", RAIZ / "datos"))
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def ruta_listas() -> Path:
    """Carpeta con las listas de medios que edita el usuario."""
    return Path(os.environ.get("VERIFICANOTICIAS_LISTAS", RAIZ / "listas"))


def ruta_listas_importadas() -> Path:
    ruta = ruta_datos() / "listas_importadas"
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def fusionar(base: dict, extra: dict) -> dict:
    """Combina dos diccionarios: los valores de ``extra`` pisan a los de ``base``.

    Los diccionarios anidados se combinan; las listas se reemplazan enteras.
    """
    resultado = copy.deepcopy(base)
    for clave, valor in (extra or {}).items():
        if isinstance(valor, dict) and isinstance(resultado.get(clave), dict):
            resultado[clave] = fusionar(resultado[clave], valor)
        else:
            resultado[clave] = copy.deepcopy(valor)
    return resultado


def _leer_yaml(ruta: Path) -> dict:
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        linea = ""
        marca = getattr(e, "problem_mark", None)
        if marca is not None:
            linea = f" (cerca de la línea {marca.line + 1})"
        raise ErrorConfig(
            f"El archivo {ruta.name} tiene un error de formato{linea}. "
            "Revisa los espacios al inicio de las líneas, o borra el archivo "
            "para volver a los valores originales."
        ) from e
    if not isinstance(datos, dict):
        raise ErrorConfig(f"El archivo {ruta.name} no tiene el formato esperado.")
    return datos


def cargar() -> dict:
    """Lee la configuración desde disco (sin usar la copia en memoria)."""
    predeterminada = _leer_yaml(ARCHIVO_PREDETERMINADO)
    ruta_usuario = ruta_config_usuario()
    if not ruta_usuario.exists():
        try:
            shutil.copyfile(ARCHIVO_PREDETERMINADO, ruta_usuario)
        except OSError:
            return predeterminada
    return fusionar(predeterminada, _leer_yaml(ruta_usuario))


def obtener() -> dict:
    """Configuración actual (se lee una sola vez y queda en memoria)."""
    global _config
    with _lock:
        if _config is None:
            _config = cargar()
        return _config


def establecer(config: dict | None) -> None:
    """Reemplaza la configuración en memoria (usado en tests y al recargar)."""
    global _config
    with _lock:
        _config = config


def valor(config: dict, ruta: str, por_defecto: Any = None) -> Any:
    """Lee un valor anidado: ``valor(cfg, "puntaje.fuente.satira")``."""
    actual: Any = config
    for parte in ruta.split("."):
        if not isinstance(actual, dict) or parte not in actual:
            return por_defecto
        actual = actual[parte]
    return actual
