"""Búsqueda en DuckDuckGo con la librería ddgs (sin API key)."""

from __future__ import annotations

from urllib.parse import urlencode

from .. import cache, config, red
from .base import Articulo, ResultadoFuente, ejecutar, fecha_iso


def _ddgs():
    from ddgs import DDGS

    timeout = int(config.valor(config.obtener(), "red.timeout_segundos", 15))
    return DDGS(timeout=timeout)


def _traducir_error(e: Exception) -> red.ErrorRed:
    from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

    if isinstance(e, RatelimitException):
        return red.ErrorRed(red.LIMITE, "DuckDuckGo limitó las búsquedas. Espera unos minutos y vuelve a intentar.")
    if isinstance(e, TimeoutException):
        return red.ErrorRed(red.TIMEOUT, "DuckDuckGo tardó demasiado en responder.")
    if isinstance(e, DDGSException):
        texto = str(e).lower()
        if "no results" in texto:
            return red.ErrorRed("sin_resultados_ddg", "La búsqueda no devolvió resultados.")
        if "ratelimit" in texto or "202" in texto or "429" in texto:
            return red.ErrorRed(red.LIMITE, "DuckDuckGo limitó las búsquedas. Espera unos minutos.")
        if not red.hay_internet():
            return red.ErrorRed(red.SIN_INTERNET)
        if "error sending request" in texto or "connect" in texto or "dns" in texto:
            return red.ErrorRed(red.SIN_CONEXION_SITIO, "No se pudo conectar con DuckDuckGo.")
        if "timed out" in texto or "timeout" in texto:
            return red.ErrorRed(red.TIMEOUT, "DuckDuckGo tardó demasiado en responder.")
        return red.ErrorRed(red.ERROR, f"DuckDuckGo no respondió ({type(e).__name__}).")
    return red.ErrorRed(red.ERROR, f"DuckDuckGo: {type(e).__name__}")


def _buscar(tipo: str, consulta: str, idioma: str, max_resultados: int) -> tuple[list[dict], bool, str]:
    opciones = config.valor(config.obtener(), "fuentes.duckduckgo", {})
    region = (opciones.get("region") or {}).get(idioma, "wt-wt")
    backend = opciones.get("backend", "duckduckgo")
    parametros = {"tipo": tipo, "q": consulta, "region": region, "max": max_resultados, "backend": backend}

    def descargar() -> list[dict]:
        try:
            cliente = _ddgs()
            if tipo == "news":
                items = cliente.news(consulta, region=region, max_results=max_resultados, backend=backend)
            else:
                items = cliente.text(consulta, region=region, max_results=max_resultados, backend=backend)
        except Exception as e:  # noqa: BLE001
            error = _traducir_error(e)
            if error.tipo == "sin_resultados_ddg":
                return []
            raise error from e
        articulos = []
        for item in items or []:
            url = item.get("url") or item.get("href")
            if not url:
                continue
            articulos.append(
                Articulo(
                    titulo=(item.get("title") or "").strip(),
                    url=url,
                    fecha=fecha_iso(item.get("date")),
                    resumen=(item.get("body") or "").strip(),
                    medio=item.get("source") or "",
                    fuente_busqueda="DuckDuckGo",
                    idioma=idioma,
                ).a_dict()
            )
        return articulos

    articulos, desde_cache = cache.con_cache("duckduckgo", parametros, cache.horas("busquedas"), descargar)
    extra = {"iar": "news", "ia": "news"} if tipo == "news" else {}
    return articulos, desde_cache, "https://duckduckgo.com/?" + urlencode({"q": consulta, **extra})


def buscar_noticias(consulta: str, idioma: str) -> ResultadoFuente:
    opciones = config.valor(config.obtener(), "fuentes.duckduckgo", {})
    if not opciones.get("activa", True):
        return ResultadoFuente(nombre="DuckDuckGo", estado="desactivada", mensaje="Desactivada en la configuración.")
    if not consulta.strip():
        return ResultadoFuente(nombre="DuckDuckGo", estado="omitida", mensaje="No hay términos suficientes para buscar.")

    def trabajo(resultado: ResultadoFuente) -> None:
        articulos, desde_cache, url = _buscar("news", consulta, idioma, int(opciones.get("max_resultados", 25)))
        resultado.articulos = articulos
        resultado.desde_cache = desde_cache
        resultado.consultas.append(url)

    return ejecutar("DuckDuckGo", trabajo)


def buscar_web(consulta: str, idioma: str, nombre: str, max_resultados: int = 20) -> ResultadoFuente:
    opciones = config.valor(config.obtener(), "fuentes.duckduckgo", {})
    if not opciones.get("activa", True):
        return ResultadoFuente(nombre=nombre, estado="desactivada", mensaje="DuckDuckGo está desactivado en la configuración.")
    if not consulta.strip():
        return ResultadoFuente(nombre=nombre, estado="omitida", mensaje="No hay términos suficientes para buscar.")

    def trabajo(resultado: ResultadoFuente) -> None:
        articulos, desde_cache, url = _buscar("text", consulta, idioma, max_resultados)
        resultado.articulos = articulos
        resultado.desde_cache = desde_cache
        resultado.consultas.append(url)

    return ejecutar(nombre, trabajo)
