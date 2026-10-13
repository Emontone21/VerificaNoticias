"""Resúmenes de Wikipedia (API pública REST, sin API key)."""

from __future__ import annotations

from urllib.parse import quote

from .. import cache, config, red


def _resumen_rest(titulo: str, idioma: str) -> dict | None:
    url = f"https://{idioma}.wikipedia.org/api/rest_v1/page/summary/{quote(titulo.replace(' ', '_'), safe='')}"
    respuesta = red.obtener(url, params={"redirect": "true"}, aceptar_404=True)
    if respuesta.status_code == 404:
        return None
    datos = respuesta.json()
    if datos.get("type") in ("disambiguation", "no-extract") or not datos.get("extract"):
        return None
    return {
        "titulo": datos.get("title") or titulo,
        "descripcion": datos.get("description") or "",
        "extracto": datos.get("extract") or "",
        "url": ((datos.get("content_urls") or {}).get("desktop") or {}).get("page")
        or f"https://{idioma}.wikipedia.org/wiki/{quote(titulo.replace(' ', '_'))}",
        "idioma": idioma,
    }


def _buscar_titulo(nombre: str, idioma: str) -> str | None:
    url = f"https://{idioma}.wikipedia.org/w/api.php"
    params = {"action": "opensearch", "search": nombre, "limit": 1, "namespace": 0, "format": "json"}
    datos = red.obtener(url, params=params).json()
    if isinstance(datos, list) and len(datos) > 1 and datos[1]:
        return datos[1][0]
    return None


def resumen(nombre: str, idioma: str = "es") -> dict | None:
    """Resumen del artículo de Wikipedia sobre ``nombre`` (o ``None``)."""
    idiomas = [idioma] + [i for i in ("es", "en") if i != idioma]

    def consultar() -> dict:
        for lang in idiomas:
            datos = _resumen_rest(nombre, lang)
            if datos is None:
                titulo = _buscar_titulo(nombre, lang)
                if titulo:
                    datos = _resumen_rest(titulo, lang)
            if datos:
                return datos
        return {}

    datos, _ = cache.con_cache("wikipedia", {"nombre": nombre, "idioma": idioma}, cache.horas("wikipedia"), consultar)
    return datos or None


def resumenes(entidades: list[dict], idioma: str) -> tuple[list[dict], list[str]]:
    """Resúmenes para varias entidades. Devuelve (resúmenes, errores)."""
    opciones = config.valor(config.obtener(), "fuentes.wikipedia", {}) or {}
    if not opciones.get("activa", True):
        return [], []
    maximo = int(opciones.get("max_entidades", 5))
    resultados: list[dict] = []
    errores: list[str] = []
    vistos: set[str] = set()
    for entidad in entidades:
        if len(resultados) >= maximo:
            break
        try:
            datos = resumen(entidad["texto"], idioma)
        except red.ErrorRed as e:
            errores.append(f"{entidad['texto']}: {e.mensaje}")
            if e.tipo in (red.SIN_INTERNET, red.LIMITE):
                break
            continue
        if datos and datos["url"] not in vistos:
            vistos.add(datos["url"])
            resultados.append({**datos, "entidad": entidad["texto"], "tipo": entidad.get("tipo", "")})
    return resultados, errores
