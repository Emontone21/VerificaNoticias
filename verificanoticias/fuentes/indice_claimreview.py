"""Índice local de verificaciones (feed público ClaimReview de Data Commons).

El feed es un archivo JSON de unos 200 MB que reúne el marcado ClaimReview de
verificadores de todo el mundo. Se descarga con "Actualizar datos" y se guarda
en una base SQLite con búsqueda de texto completo (FTS5), así las consultas
son locales e instantáneas.
"""

from __future__ import annotations

import collections
import csv
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .. import config, red, texto
from . import claimreview
from .base import dominio_de

NOMBRE_FUENTE = "Base local ClaimReview"
_lock = threading.Lock()


def ruta_db() -> Path:
    return config.ruta_datos() / "claimreview.db"


def _fts_disponible(con: sqlite3.Connection) -> bool:
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.prueba_fts USING fts5(x)")
        con.execute("DROP TABLE IF EXISTS temp.prueba_fts")
        return True
    except sqlite3.OperationalError:
        return False


def info() -> dict:
    """Estado del índice: si existe, cuántas verificaciones tiene y su fecha."""
    ruta = ruta_db()
    datos = {"disponible": False, "cantidad": 0, "fecha_actualizacion": None, "dias": None, "desactualizado": True}
    if not ruta.exists():
        return datos
    try:
        con = sqlite3.connect(ruta)
        try:
            meta = dict(con.execute("SELECT clave, valor FROM meta").fetchall())
        finally:
            con.close()
    except sqlite3.Error:
        return datos
    fecha = meta.get("fecha_actualizacion")
    dias = None
    if fecha:
        try:
            dias = (datetime.now(timezone.utc) - datetime.fromisoformat(fecha)).days
        except ValueError:
            dias = None
    limite = int(config.valor(config.obtener(), "fuentes.claimreview_feed.dias_para_sugerir_actualizar", 7))
    datos.update(
        disponible=True,
        cantidad=int(meta.get("cantidad", 0)),
        fecha_actualizacion=fecha,
        dias=dias,
        desactualizado=dias is None or dias > limite,
        fts=meta.get("fts") == "1",
    )
    return datos


def _consulta_fts(terminos: list[str], max_palabras: int = 14) -> str:
    partes: list[str] = []
    vistas: set[str] = set()
    for termino in terminos:
        palabras = [p for p in texto.normalizar(termino).split() if len(p) >= 3 and p not in texto.STOPWORDS]
        if not palabras:
            continue
        frase = " ".join(palabras)
        if frase in vistas:
            continue
        vistas.add(frase)
        partes.append(f'"{frase}"')
        if len(palabras) > 1:  # además de la frase, cada palabra suelta
            for p in palabras:
                if p not in vistas:
                    vistas.add(p)
                    partes.append(f'"{p}"')
        if len(partes) >= max_palabras:
            break
    return " OR ".join(partes[:max_palabras])


def buscar(terminos: list[str], limite: int | None = None) -> list[dict]:
    """Verificaciones del índice que comparten términos con la noticia."""
    ruta = ruta_db()
    if not ruta.exists():
        return []
    if limite is None:
        limite = int(config.valor(config.obtener(), "fuentes.claimreview_feed.max_candidatos", 150))
    consulta = _consulta_fts(terminos)
    if not consulta:
        return []
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    try:
        meta = dict(con.execute("SELECT clave, valor FROM meta").fetchall())
        if meta.get("fts") == "1":
            filas = con.execute(
                "SELECT v.* FROM verificaciones_fts f JOIN verificaciones v ON v.id = f.rowid"
                " WHERE verificaciones_fts MATCH ? ORDER BY bm25(verificaciones_fts) LIMIT ?",
                (consulta, limite),
            ).fetchall()
        else:  # SQLite sin FTS5: búsqueda simple y más lenta
            palabras = [p.strip('"') for p in consulta.split(" OR ")][:3]
            condicion = " OR ".join("afirmacion_norm LIKE ?" for _ in palabras)
            filas = con.execute(
                f"SELECT * FROM verificaciones WHERE {condicion} LIMIT ?",
                [*(f"%{p}%" for p in palabras), limite],
            ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    resultados = []
    for fila in filas:
        d = dict(fila)
        d.pop("afirmacion_norm", None)
        d.pop("id", None)
        d["apariciones"] = [a for a in (d.pop("aparicion", "") or "").split("\n") if a]
        d["origen"] = NOMBRE_FUENTE
        resultados.append(d)
    return resultados


# ----------------------------------------------------------------------
# Construcción del índice
# ----------------------------------------------------------------------

_COLUMNAS = ("afirmacion", "afirmacion_norm", "veredicto", "valor", "mejor", "peor", "explicacion",
             "organizacion", "url_organizacion", "url", "dominio", "fecha", "autor_afirmacion",
             "fecha_afirmacion", "aparicion")


def _crear_tablas(con: sqlite3.Connection) -> bool:
    con.execute("CREATE TABLE meta (clave TEXT PRIMARY KEY, valor TEXT)")
    con.execute(
        "CREATE TABLE verificaciones (id INTEGER PRIMARY KEY, afirmacion TEXT, afirmacion_norm TEXT,"
        " veredicto TEXT, valor TEXT, mejor TEXT, peor TEXT, explicacion TEXT, organizacion TEXT,"
        " url_organizacion TEXT, url TEXT, dominio TEXT, fecha TEXT, autor_afirmacion TEXT,"
        " fecha_afirmacion TEXT, aparicion TEXT, UNIQUE(url, afirmacion))"
    )
    if not _fts_disponible(con):
        return False
    for tokenizador in ("unicode61 remove_diacritics 2", "unicode61 remove_diacritics 1"):
        try:
            con.execute(
                "CREATE VIRTUAL TABLE verificaciones_fts USING fts5(afirmacion, content='verificaciones',"
                f" content_rowid='id', tokenize='{tokenizador}')"
            )
            return True
        except sqlite3.OperationalError:
            continue
    return False


def construir(ruta_json: Path, ruta_salida: Path, progreso: Callable[[str], None] | None = None) -> dict:
    """Lee el feed (sin cargarlo entero en memoria) y crea la base SQLite."""
    import ijson

    if ruta_salida.exists():
        ruta_salida.unlink()
    con = sqlite3.connect(ruta_salida)
    publicadores: collections.Counter = collections.Counter()
    nombres: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    total = 0
    try:
        fts = _crear_tablas(con)
        lote: list[tuple] = []
        with open(ruta_json, "rb") as f:
            for elemento in ijson.items(f, "dataFeedElement.item"):
                if not isinstance(elemento, dict):
                    continue
                items = elemento.get("item")
                for cr in items if isinstance(items, list) else [items]:
                    v = claimreview.normalizar(cr) if isinstance(cr, dict) else None
                    if not v or not v["afirmacion"]:
                        continue
                    total += 1
                    if v["dominio"]:
                        publicadores[v["dominio"]] += 1
                        if v["organizacion"]:
                            nombres[v["dominio"]][v["organizacion"]] += 1
                    lote.append((
                        v["afirmacion"][:2000], "" if fts else texto.normalizar(v["afirmacion"])[:2000],
                        v["veredicto"][:300],
                        _texto_o_none(v["valor"]), _texto_o_none(v["mejor"]), _texto_o_none(v["peor"]),
                        v["explicacion"][:1000], v["organizacion"][:200], v["url_organizacion"][:300], v["url"][:1000],
                        v["dominio"], v["fecha"], v["autor_afirmacion"][:200], v["fecha_afirmacion"],
                        "\n".join(v["apariciones"])[:2000],
                    ))
                    if len(lote) >= 2000:
                        _insertar(con, lote)
                        lote = []
                        if progreso:
                            progreso(f"Procesando verificaciones: {total:,}".replace(",", "."))
        _insertar(con, lote)
        cantidad = con.execute("SELECT COUNT(*) FROM verificaciones").fetchone()[0]
        if fts:
            if progreso:
                progreso("Creando el índice de búsqueda…")
            con.execute("INSERT INTO verificaciones_fts(verificaciones_fts) VALUES('rebuild')")
        ahora = datetime.now(timezone.utc).isoformat()
        con.executemany(
            "INSERT INTO meta (clave, valor) VALUES (?, ?)",
            [("fecha_actualizacion", ahora), ("cantidad", str(cantidad)), ("fts", "1" if fts else "0")],
        )
        con.commit()
    finally:
        con.close()
    return {
        "cantidad": cantidad,
        "leidas": total,
        "publicadores": [
            (dominio, n, nombres[dominio].most_common(1)[0][0] if nombres[dominio] else "")
            for dominio, n in publicadores.most_common()
        ],
    }


def _texto_o_none(valor) -> str | None:
    return None if valor in (None, "") else str(valor)


def _insertar(con: sqlite3.Connection, lote: list[tuple]) -> None:
    if lote:
        con.executemany(
            f"INSERT OR IGNORE INTO verificaciones ({', '.join(_COLUMNAS)}) VALUES ({', '.join('?' * len(_COLUMNAS))})",
            lote,
        )


def guardar_verificadores_del_feed(publicadores: list[tuple], minimo: int) -> int:
    """Guarda los dominios que publican verificaciones en el feed (lista importada)."""
    ruta = config.ruta_listas_importadas() / "verificadores_feed.csv"
    filas = [(d, nombre, n) for d, n, nombre in publicadores if n >= minimo]
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["dominio", "nombre", "verificaciones_en_feed"])
        escritor.writerows(filas)
    return len(filas)


def actualizar(progreso: Callable[[str], None] | None = None) -> dict:
    """Descarga el feed, reconstruye el índice y reemplaza el anterior."""
    with _lock:
        cfg = config.obtener()
        url = config.valor(cfg, "fuentes.claimreview_feed.url")
        carpeta = config.ruta_datos() / "descargas"
        carpeta.mkdir(parents=True, exist_ok=True)
        archivo = carpeta / "claimreview.json"
        inicio = time.time()

        def avance(bytes_, total):
            if progreso:
                mb = bytes_ / 1024 / 1024
                if total:
                    progreso(f"Descargando verificaciones: {mb:.0f} de {total / 1024 / 1024:.0f} MB")
                else:
                    progreso(f"Descargando verificaciones: {mb:.0f} MB")

        if progreso:
            progreso("Conectando para descargar el feed ClaimReview…")
        red.descargar_archivo(url, archivo, avance, timeout=120)
        nueva = config.ruta_datos() / "claimreview_nuevo.db"
        try:
            estadisticas = construir(archivo, nueva, progreso)
        except Exception as e:  # noqa: BLE001
            if nueva.exists():
                nueva.unlink()
            raise red.ErrorRed(red.RESPUESTA_INVALIDA, f"No se pudo procesar el feed descargado: {e}") from e
        finally:
            if archivo.exists():
                archivo.unlink()
        if estadisticas["cantidad"] == 0:
            nueva.unlink()
            raise red.ErrorRed(red.RESPUESTA_INVALIDA, "El feed descargado no contenía verificaciones.")
        os.replace(nueva, ruta_db())
        minimo = int(config.valor(cfg, "listas_publicas.verificadores_del_feed.minimo_verificaciones", 5))
        n_verificadores = 0
        if config.valor(cfg, "listas_publicas.verificadores_del_feed.activa", True):
            n_verificadores = guardar_verificadores_del_feed(estadisticas["publicadores"], minimo)
        return {
            "cantidad": estadisticas["cantidad"],
            "verificadores_detectados": n_verificadores,
            "segundos": round(time.time() - inicio, 1),
        }


def dominios_verificadores_del_feed() -> list[str]:
    ruta = config.ruta_listas_importadas() / "verificadores_feed.csv"
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8") as f:
        return [fila["dominio"] for fila in csv.DictReader(f) if fila.get("dominio")]


__all__ = ["buscar", "info", "actualizar", "construir", "NOMBRE_FUENTE", "dominio_de"]
