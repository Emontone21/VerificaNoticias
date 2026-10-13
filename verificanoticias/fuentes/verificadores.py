"""Búsqueda en vivo de artículos de verificadores y lectura de su ClaimReview."""

from __future__ import annotations

import concurrent.futures

from .. import cache, config, red, similitud
from . import claimreview, duckduckgo
from .base import ResultadoFuente, ejecutar


def buscar_en_duckduckgo(consulta: str, idioma: str) -> ResultadoFuente:
    """Búsqueda web pensada para encontrar verificaciones de la noticia."""
    sufijo = "falso verificación" if idioma == "es" else "fact check"
    return duckduckgo.buscar_web(f"{consulta} {sufijo}".strip(), idioma, nombre="DuckDuckGo (verificadores)")


def _leer_pagina(url: str) -> dict:
    """Descarga una página de verificador y devuelve sus ClaimReview (con caché)."""

    def descargar() -> dict:
        respuesta = red.obtener(url, tipo="navegador")
        return {"verificaciones": claimreview.extraer_de_html(respuesta.content, respuesta.url), "url_final": respuesta.url}

    datos, _ = cache.con_cache("pagina_verificador", url, cache.horas("verificadores"), descargar)
    return datos


def leer_paginas(candidatos: list[dict], referencia: str) -> ResultadoFuente:
    """Lee el marcado ClaimReview de las páginas de verificadores más parecidas a la noticia.

    ``candidatos``: artículos (de cualquier buscador) publicados por verificadores.
    En ``extra`` devuelve ``verificaciones`` (con ClaimReview) y ``sin_marcado``
    (artículos de verificadores sin ClaimReview legible).
    """
    opciones = config.valor(config.obtener(), "fuentes.verificadores", {}) or {}
    if not opciones.get("buscar_en_vivo", True):
        return ResultadoFuente(nombre="Páginas de verificadores", estado="desactivada",
                               mensaje="Desactivada en la configuración.")
    maximo = int(opciones.get("max_paginas_a_leer", 6))

    unicos: dict[str, dict] = {}
    for c in candidatos:
        if c.get("url") and c["url"] not in unicos:
            unicos[c["url"]] = c
    lista = list(unicos.values())
    if not lista:
        return ResultadoFuente(nombre="Páginas de verificadores", estado="sin_resultados",
                               mensaje="No se encontraron artículos de verificadores sobre el tema.")
    puntajes = similitud.similitudes(referencia, [f"{c.get('titulo', '')} {c.get('resumen', '')}" for c in lista])
    for c, p in zip(lista, puntajes):
        c["similitud"] = p
    lista.sort(key=lambda c: c["similitud"], reverse=True)
    # Los enlaces de Google News son redirecciones que no se pueden leer directamente.
    a_leer = [c for c in lista if "news.google.com" not in c["url"]][:maximo]
    no_legibles = [c for c in lista if "news.google.com" in c["url"]]

    def trabajo(resultado: ResultadoFuente) -> None:
        verificaciones: list[dict] = []
        sin_marcado: list[dict] = []
        errores: list[str] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ejecutor:
            futuros = {ejecutor.submit(_leer_pagina, c["url"]): c for c in a_leer}
            for futuro in concurrent.futures.as_completed(futuros):
                candidato = futuros[futuro]
                resultado.consultas.append(candidato["url"])
                try:
                    datos = futuro.result()
                except red.ErrorRed as e:
                    errores.append(f"{candidato.get('dominio', '')}: {e.mensaje}")
                    sin_marcado.append({**candidato, "error": e.mensaje})
                    continue
                encontradas = datos.get("verificaciones") or []
                if encontradas:
                    for v in encontradas:
                        verificaciones.append({**v, "origen": "Página del verificador", "url_pagina": candidato["url"]})
                else:
                    sin_marcado.append(candidato)
        for c in no_legibles:
            sin_marcado.append(c)
        for c in sin_marcado:
            c["veredicto_titulo"] = claimreview.veredicto_desde_titulo(c.get("titulo", ""))
        resultado.extra = {"verificaciones": verificaciones, "sin_marcado": sin_marcado, "con_datos": True}
        resultado.articulos = [{"titulo": c.get("titulo", ""), "url": c["url"], "dominio": c.get("dominio", "")}
                               for c in a_leer]
        if errores:
            resultado.mensaje = f"{len(errores)} página(s) no se pudieron leer: " + "; ".join(errores[:3])

    return ejecutar("Páginas de verificadores", trabajo)
