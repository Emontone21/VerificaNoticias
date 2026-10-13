"""Búsqueda en la API DOC 2.0 de GDELT (gratuita, sin API key).

Documentación: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
"""

from __future__ import annotations

import re
import threading
import time

import httpx

from .. import cache, config, red
from .base import Articulo, ResultadoFuente, ejecutar, fecha_iso

URL = "https://api.gdeltproject.org/api/v2/doc/doc"
IDIOMAS = {"es": "spanish", "en": "english"}

_lock = threading.Lock()
_ultima_consulta = [0.0]


def _limpiar_termino(termino: str) -> str:
    termino = re.sub(r"[^\w\s-]", " ", termino, flags=re.UNICODE)
    return " ".join(p for p in termino.split() if len(p) >= 3)


def armar_consulta(terminos: list[str], max_terminos: int = 4) -> str:
    partes: list[str] = []
    for termino in terminos:
        limpio = _limpiar_termino(termino)
        if not limpio:
            continue
        partes.append(f'"{limpio}"' if " " in limpio else limpio)
        if len(partes) >= max_terminos:
            break
    return " ".join(partes)


def _esperar_turno(segundos: float) -> None:
    """GDELT pide no hacer más de una consulta cada 5 segundos."""
    espera = _ultima_consulta[0] + segundos - time.time()
    if espera > 0:
        time.sleep(espera)


def _interpretar(texto: str) -> list[dict]:
    texto = texto.strip()
    if not texto.startswith("{"):
        mensaje = texto[:200] or "Respuesta vacía"
        if "limit requests" in texto.lower():
            raise red.ErrorRed(red.LIMITE, "GDELT pide esperar entre consultas (límite de 1 cada 5 segundos).")
        raise red.ErrorRed(red.RESPUESTA_INVALIDA, f"GDELT no aceptó la consulta: {mensaje}")
    import json

    try:
        datos = json.loads(texto, strict=False)
    except json.JSONDecodeError as e:
        raise red.ErrorRed(red.RESPUESTA_INVALIDA, "GDELT devolvió datos con formato inválido.") from e
    return datos.get("articles") or []


def _convertir(items: list[dict], idioma: str) -> list[dict]:
    articulos = []
    for item in items:
        url = item.get("url")
        if not url:
            continue
        articulos.append(
            Articulo(
                titulo=(item.get("title") or "").strip(),
                url=url,
                dominio=(item.get("domain") or "").lower().removeprefix("www."),
                fecha=fecha_iso(item.get("seendate")),
                medio=item.get("domain") or "",
                fuente_busqueda="GDELT",
                idioma=idioma,
            ).a_dict()
        )
    return articulos


def buscar(consulta: str, idioma: str, nombre: str = "GDELT", periodo: str | None = None) -> ResultadoFuente:
    cfg = config.obtener()
    opciones = config.valor(cfg, "fuentes.gdelt", {})
    if not opciones.get("activa", True):
        return ResultadoFuente(nombre=nombre, estado="desactivada", mensaje="Desactivada en la configuración.")
    if not consulta.strip():
        return ResultadoFuente(nombre=nombre, estado="omitida", mensaje="No hay términos suficientes para buscar.")

    def trabajo(resultado: ResultadoFuente) -> None:
        q = consulta
        if idioma in IDIOMAS:
            q = f"{q} sourcelang:{IDIOMAS[idioma]}"
        params = {
            "query": q,
            "mode": "artlist",
            "format": "json",
            "maxrecords": int(opciones.get("max_resultados", 75)),
            "sort": "hybridrel",
            "timespan": periodo or opciones.get("periodo", "3months"),
        }
        resultado.consultas.append(str(httpx.URL(URL, params=params)))

        def descargar() -> list[dict]:
            with _lock:
                _esperar_turno(float(opciones.get("segundos_entre_consultas", 5.5)))
                try:
                    respuesta = red.obtener(URL, params=params)
                finally:
                    _ultima_consulta[0] = time.time()
            return _convertir(_interpretar(respuesta.text), idioma)

        articulos, desde_cache = cache.con_cache("gdelt", params, cache.horas("busquedas"), descargar)
        resultado.articulos = articulos
        resultado.desde_cache = desde_cache

    return ejecutar(nombre, trabajo)


def buscar_en_dominios(terminos_consulta: str, dominios: list[str], idioma: str) -> ResultadoFuente:
    """Busca solo dentro de una lista de dominios (por ejemplo, verificadores)."""
    dominios = [d for d in dominios if d and "/" not in d][:20]
    if not dominios or not terminos_consulta.strip():
        return ResultadoFuente(nombre="GDELT (verificadores)", estado="omitida", mensaje="Sin términos o dominios.")
    filtro = " OR ".join(f"domainis:{d}" for d in dominios)
    return buscar(f"{terminos_consulta} ({filtro})", idioma, nombre="GDELT (verificadores)")
