"""Caché local de consultas en SQLite, para no repetir búsquedas iguales."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

from . import config

_lock = threading.Lock()


def _ruta() -> Path:
    return config.ruta_datos() / "cache.db"


def _conectar() -> sqlite3.Connection:
    con = sqlite3.connect(_ruta(), timeout=10)
    con.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        " clave TEXT PRIMARY KEY, espacio TEXT, valor TEXT, creado REAL, expira REAL)"
    )
    return con


def _clave(espacio: str, parametros: Any) -> str:
    texto = espacio + "|" + json.dumps(parametros, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def obtener(espacio: str, parametros: Any) -> Any | None:
    """Devuelve el valor guardado o ``None`` si no existe o ya venció."""
    clave = _clave(espacio, parametros)
    with _lock:
        con = _conectar()
        try:
            fila = con.execute("SELECT valor, expira FROM cache WHERE clave = ?", (clave,)).fetchone()
        finally:
            con.close()
    if not fila or fila[1] < time.time():
        return None
    try:
        return json.loads(fila[0])
    except json.JSONDecodeError:
        return None


def guardar(espacio: str, parametros: Any, valor: Any, horas: float) -> None:
    if horas <= 0:
        return
    clave = _clave(espacio, parametros)
    ahora = time.time()
    with _lock:
        con = _conectar()
        try:
            con.execute(
                "INSERT OR REPLACE INTO cache (clave, espacio, valor, creado, expira) VALUES (?, ?, ?, ?, ?)",
                (clave, espacio, json.dumps(valor, ensure_ascii=False, default=str), ahora, ahora + horas * 3600),
            )
            con.commit()
        finally:
            con.close()


def con_cache(espacio: str, parametros: Any, horas: float, funcion: Callable[[], Any]) -> tuple[Any, bool]:
    """Ejecuta ``funcion`` solo si el resultado no está en caché.

    Devuelve ``(valor, vino_de_cache)``. Los errores no se guardan.
    """
    guardado = obtener(espacio, parametros)
    if guardado is not None:
        return guardado, True
    valor = funcion()
    guardar(espacio, parametros, valor, horas)
    return valor, False


def horas(tipo: str) -> float:
    return float(config.valor(config.obtener(), f"cache_horas.{tipo}", 6))


def limpiar_vencidos() -> int:
    with _lock:
        con = _conectar()
        try:
            cursor = con.execute("DELETE FROM cache WHERE expira < ?", (time.time(),))
            con.commit()
            return cursor.rowcount
        finally:
            con.close()


def vaciar() -> None:
    with _lock:
        con = _conectar()
        try:
            con.execute("DELETE FROM cache")
            con.commit()
        finally:
            con.close()
