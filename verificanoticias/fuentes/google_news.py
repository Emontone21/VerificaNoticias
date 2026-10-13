"""Búsqueda en el RSS público de Google News (sin API key)."""

from __future__ import annotations

import feedparser
import httpx

from .. import cache, config, red
from .base import Articulo, ResultadoFuente, dominio_de, ejecutar, fecha_iso

URL = "https://news.google.com/rss/search"


def _titulo_sin_medio(titulo: str, medio: str) -> str:
    """Google News agrega " - Medio" al final de cada titular."""
    titulo = (titulo or "").strip()
    if medio and titulo.endswith(f" - {medio}"):
        return titulo[: -len(f" - {medio}")].strip()
    if " - " in titulo:
        return titulo.rsplit(" - ", 1)[0].strip()
    return titulo


def interpretar_rss(contenido: bytes | str, idioma: str) -> list[dict]:
    feed = feedparser.parse(contenido)
    if feed.bozo and not feed.entries:
        raise red.ErrorRed(red.RESPUESTA_INVALIDA, "Google News devolvió un RSS inválido.")
    articulos = []
    for entrada in feed.entries:
        fuente = entrada.get("source") or {}
        medio = fuente.get("title", "") if isinstance(fuente, dict) else ""
        sitio = fuente.get("href", "") if isinstance(fuente, dict) else ""
        enlace = entrada.get("link", "")
        if not enlace:
            continue
        articulos.append(
            Articulo(
                titulo=_titulo_sin_medio(entrada.get("title", ""), medio),
                url=enlace,
                dominio=dominio_de(sitio) if sitio else "",
                fecha=fecha_iso(entrada.get("published_parsed") or entrada.get("published")),
                medio=medio,
                fuente_busqueda="Google News",
                idioma=idioma,
            ).a_dict()
        )
    return articulos


def buscar(consulta: str, idioma: str) -> ResultadoFuente:
    cfg = config.obtener()
    opciones = config.valor(cfg, "fuentes.google_news", {})
    if not opciones.get("activa", True):
        return ResultadoFuente(nombre="Google News", estado="desactivada", mensaje="Desactivada en la configuración.")
    if not consulta.strip():
        return ResultadoFuente(nombre="Google News", estado="omitida", mensaje="No hay términos suficientes para buscar.")
    ediciones = (opciones.get("ediciones") or {}).get(idioma) or (opciones.get("ediciones") or {}).get("es") or []

    def trabajo(resultado: ResultadoFuente) -> None:
        vistos: set[str] = set()
        errores: list[red.ErrorRed] = []
        alguna_cache = False
        for edicion in ediciones:
            params = {"q": consulta, "hl": edicion["hl"], "gl": edicion["gl"], "ceid": edicion["ceid"]}
            resultado.consultas.append(str(httpx.URL(URL, params=params)))

            def descargar(params=params) -> list[dict]:
                respuesta = red.obtener(URL, params=params, tipo="navegador")
                return interpretar_rss(respuesta.content, idioma)

            try:
                articulos, desde_cache = cache.con_cache("google_news", params, cache.horas("busquedas"), descargar)
            except red.ErrorRed as e:
                errores.append(e)
                continue
            alguna_cache = alguna_cache or desde_cache
            for articulo in articulos:
                if articulo["url"] not in vistos:
                    vistos.add(articulo["url"])
                    resultado.articulos.append(articulo)
        resultado.desde_cache = alguna_cache
        if errores and len(errores) == len(ediciones):
            raise errores[0]
        if errores:
            resultado.mensaje = f"Una edición falló: {errores[0].mensaje}"

    return ejecutar("Google News", trabajo)
