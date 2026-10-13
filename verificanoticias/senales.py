"""Detección de señales de alerta en el texto (heurísticas transparentes)."""

from __future__ import annotations

import re

from . import config, similitud, texto
from .extraccion import Noticia

_RE_CITA = re.compile(r"[\"“«]([^\"”»]{20,400})[\"”»]")


def _mayusculas(contenido: str) -> tuple[float, list[str]]:
    palabras = [p for p in texto.palabras(contenido) if len(p) >= 4 and any(c.isalpha() for c in p)]
    if not palabras:
        return 0.0, []
    mayus = [p for p in palabras if p.isupper()]
    return round(len(mayus) / len(palabras), 2), mayus


def _expresiones(cfg: dict, clave: str, idioma: str, ambos: bool = False) -> list[str]:
    tabla = config.valor(cfg, f"alertas.{clave}", {}) or {}
    if ambos:
        return list(tabla.get("es") or []) + list(tabla.get("en") or [])
    return list(tabla.get(idioma) or tabla.get("es") or [])


def detectar(noticia: Noticia, cfg: dict | None = None) -> dict:
    """Devuelve los hechos detectados (sin puntajes: eso lo decide ``puntaje.py``)."""
    cfg = cfg or config.obtener()
    a = config.valor(cfg, "alertas", {}) or {}
    titulo, cuerpo, idioma = noticia.titulo or "", noticia.cuerpo or "", noticia.idioma
    minimo = int(a.get("minimo_caracteres_cuerpo", 300))
    cuerpo_suficiente = len(cuerpo) >= minimo
    resultado: dict = {"cuerpo_suficiente": cuerpo_suficiente}

    # Mayúsculas
    prop_titulo, mayus_titulo = _mayusculas(titulo)
    prop_cuerpo, mayus_cuerpo = _mayusculas(cuerpo) if cuerpo_suficiente else (0.0, [])
    resultado["mayusculas"] = {
        "detectada": (prop_titulo >= float(a.get("mayusculas_proporcion_titular", 0.3)) and len(mayus_titulo) >= 2)
        or prop_cuerpo >= float(a.get("mayusculas_proporcion_cuerpo", 0.08)),
        "proporcion_titulo": prop_titulo,
        "proporcion_cuerpo": prop_cuerpo,
        "ejemplos": list(dict.fromkeys(mayus_titulo + mayus_cuerpo))[:6],
    }

    # Exclamaciones
    excl_titulo = titulo.count("!") + titulo.count("¡")
    excl_cuerpo = cuerpo.count("!") + cuerpo.count("¡")
    por_mil = round(excl_cuerpo / max(len(cuerpo), 1) * 1000, 1) if cuerpo_suficiente else 0.0
    resultado["exclamaciones"] = {
        "detectada": excl_titulo >= int(a.get("exclamaciones_titular", 2))
        or "!!" in titulo + cuerpo or "¡¡" in titulo + cuerpo
        or por_mil >= float(a.get("exclamaciones_cada_1000_caracteres", 3)),
        "en_titulo": excl_titulo,
        "en_texto": excl_cuerpo,
        "cada_1000": por_mil,
    }

    # Palabras gancho (se buscan en ambos idiomas)
    resultado["palabras_gancho"] = texto.buscar_expresiones(
        f"{titulo}\n{cuerpo[:5000]}", _expresiones(cfg, "palabras_gancho", idioma, ambos=True)
    )

    # Autor y fecha (solo cuando se analizó una página)
    evaluar_metadatos = noticia.tipo == "url" and noticia.tiene_texto
    resultado["autor"] = {"evaluado": evaluar_metadatos, "valor": noticia.autor}
    resultado["fecha"] = {"evaluado": evaluar_metadatos, "valor": noticia.fecha}

    # Fuentes citadas
    atribuciones = texto.buscar_expresiones(cuerpo, _expresiones(cfg, "atribuciones", idioma)) if cuerpo else []
    citas = _RE_CITA.findall(cuerpo) if cuerpo else []
    resultado["fuentes_citadas"] = {
        "evaluado": cuerpo_suficiente,
        "atribuciones": atribuciones[:8],
        "citas_textuales": len(citas),
        "cantidad": len(atribuciones) + len(citas),
    }

    # Titular vs. cuerpo
    cobertura = similitud.cobertura_de_palabras(titulo, cuerpo) if cuerpo_suficiente else None
    resultado["titular_cuerpo"] = {
        "evaluado": cobertura is not None,
        "proporcion": cobertura,
        "detectada": cobertura is not None and cobertura < float(config.valor(cfg, "similitud.titular_cuerpo_minimo", 0.3)),
    }

    # Afirmación de alto impacto y palabras de actualidad
    inicio = f"{titulo}\n{cuerpo[:1500]}"
    resultado["alto_impacto"] = texto.buscar_expresiones(inicio, _expresiones(cfg, "palabras_alto_impacto", idioma))
    resultado["palabras_actualidad"] = texto.buscar_expresiones(inicio, _expresiones(cfg, "palabras_actualidad", idioma))
    return resultado
