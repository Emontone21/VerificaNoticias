"""Historial de análisis guardado localmente en SQLite."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from . import config

_lock = threading.Lock()


def _ruta() -> Path:
    return config.ruta_datos() / "historial.db"


def _conectar() -> sqlite3.Connection:
    con = sqlite3.connect(_ruta(), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute(
        "CREATE TABLE IF NOT EXISTS analisis ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " fecha TEXT NOT NULL,"
        " entrada TEXT NOT NULL,"
        " titulo TEXT,"
        " puntaje INTEGER,"
        " etiqueta TEXT,"
        " clave_etiqueta TEXT,"
        " resultado TEXT NOT NULL)"
    )
    return con


def guardar(resultado: dict) -> int:
    with _lock:
        con = _conectar()
        try:
            cursor = con.execute(
                "INSERT INTO analisis (fecha, entrada, titulo, puntaje, etiqueta, clave_etiqueta, resultado)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    resultado.get("fecha_analisis"),
                    resultado.get("entrada", "")[:2000],
                    (resultado.get("noticia") or {}).get("titulo"),
                    (resultado.get("resultado") or {}).get("puntaje"),
                    (resultado.get("resultado") or {}).get("etiqueta"),
                    (resultado.get("resultado") or {}).get("clave_etiqueta"),
                    json.dumps(resultado, ensure_ascii=False, default=str),
                ),
            )
            con.commit()
            return int(cursor.lastrowid)
        finally:
            con.close()


def listar(limite: int = 200) -> list[dict]:
    with _lock:
        con = _conectar()
        try:
            filas = con.execute(
                "SELECT id, fecha, entrada, titulo, puntaje, etiqueta, clave_etiqueta"
                " FROM analisis ORDER BY id DESC LIMIT ?",
                (limite,),
            ).fetchall()
        finally:
            con.close()
    return [dict(f) for f in filas]


def obtener(id_analisis: int) -> dict | None:
    with _lock:
        con = _conectar()
        try:
            fila = con.execute("SELECT id, resultado FROM analisis WHERE id = ?", (id_analisis,)).fetchone()
        finally:
            con.close()
    if not fila:
        return None
    resultado = json.loads(fila["resultado"])
    resultado["id"] = fila["id"]
    return resultado


def borrar(id_analisis: int) -> bool:
    with _lock:
        con = _conectar()
        try:
            cursor = con.execute("DELETE FROM analisis WHERE id = ?", (id_analisis,))
            con.commit()
            return cursor.rowcount > 0
        finally:
            con.close()


def borrar_todo() -> int:
    with _lock:
        con = _conectar()
        try:
            cursor = con.execute("DELETE FROM analisis")
            con.commit()
            return cursor.rowcount
        finally:
            con.close()
