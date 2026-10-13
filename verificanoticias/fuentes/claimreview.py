"""Lectura del marcado schema.org ClaimReview (JSON-LD) y de sus veredictos."""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

from .. import config, texto
from .base import dominio_de, fecha_iso

# Categorías de veredicto, de más grave a menos grave.
FALSO = "falso"
ENGANOSO = "enganoso"
SIN_EVIDENCIA = "sin_evidencia"
SATIRA = "satira"
MAYORMENTE_VERDADERO = "mayormente_verdadero"
VERDADERO = "verdadero"
DESCONOCIDO = "desconocido"

NOMBRES = {
    FALSO: "Falso",
    ENGANOSO: "Engañoso / parcialmente falso",
    SIN_EVIDENCIA: "Sin evidencia",
    SATIRA: "Sátira (humor)",
    MAYORMENTE_VERDADERO: "Mayormente verdadero",
    VERDADERO: "Verdadero",
    DESCONOCIDO: "Veredicto no reconocido",
}
NEGATIVOS = (FALSO, ENGANOSO, SIN_EVIDENCIA, SATIRA)
POSITIVOS = (MAYORMENTE_VERDADERO, VERDADERO)
_DESEMPATE = [ENGANOSO, MAYORMENTE_VERDADERO, SIN_EVIDENCIA, SATIRA, FALSO, VERDADERO]


def clasificar_veredicto(
    veredicto: str | None,
    valor: Any = None,
    mejor: Any = None,
    peor: Any = None,
    diccionario: dict | None = None,
) -> str:
    """Convierte el texto (o el número) del veredicto en una categoría.

    Si una expresión está dentro de otra más larga, gana la más larga: "parcialmente
    falso" gana sobre "falso" y "not true" sobre "true". Si hay varias expresiones
    separadas ("Falso / No hay evidencia"), gana la que aparece primero.
    """
    if diccionario is None:
        diccionario = config.valor(config.obtener(), "veredictos", {}) or {}
    norm = f" {texto.normalizar(veredicto or '')} "
    coincidencias: list[tuple[int, int, str]] = []  # (inicio, fin, categoría)
    if norm.strip():
        for categoria, expresiones in diccionario.items():
            for expresion in expresiones or []:
                e = texto.normalizar(expresion)
                if not e:
                    continue
                inicio = norm.find(f" {e} ")
                while inicio != -1:
                    coincidencias.append((inicio, inicio + len(e) + 1, categoria))
                    inicio = norm.find(f" {e} ", inicio + 1)
    # Descartar las coincidencias contenidas en otra más larga.
    validas = [c for c in coincidencias
               if not any(o[0] <= c[0] and c[1] <= o[1] and (o[1] - o[0]) > (c[1] - c[0]) for o in coincidencias)]
    if validas:
        validas.sort(key=lambda c: (c[0], -(c[1] - c[0]),
                                    _DESEMPATE.index(c[2]) if c[2] in _DESEMPATE else 99))
        return validas[0][2]
    try:
        v, b, w = float(valor), float(mejor if mejor not in (None, "") else 5), float(peor if peor not in (None, "") else 1)
    except (TypeError, ValueError):
        return DESCONOCIDO
    if b == w:
        return DESCONOCIDO
    fraccion = (v - w) / (b - w)
    if fraccion <= 0.2:
        return FALSO
    if fraccion < 0.6:
        return ENGANOSO
    if fraccion >= 0.8:
        return VERDADERO
    return MAYORMENTE_VERDADERO


def veredicto_desde_titulo(titulo: str, diccionario: dict | None = None) -> str | None:
    """Intenta deducir un veredicto negativo del titular de un artículo de verificador.

    Solo mira el comienzo del título ("Es falso que...", "Falso: ...", "#Bulo") para
    ser prudente. Devuelve ``None`` si no hay una indicación clara.
    """
    norm = texto.normalizar(titulo)
    if not norm:
        return None
    if re.search(r"\b(es falso que|is false|false claim|fake claim|bulo|hoax|no es cierto que|es mentira que)\b", norm):
        return FALSO
    comienzo = " ".join(norm.split()[:4])
    categoria = clasificar_veredicto(comienzo, diccionario=diccionario)
    if categoria in (FALSO, ENGANOSO):
        return categoria
    return None


# ----------------------------------------------------------------------
# Extracción de JSON-LD
# ----------------------------------------------------------------------

def _tipos(objeto: dict) -> list[str]:
    tipo = objeto.get("@type")
    if isinstance(tipo, list):
        return [str(t) for t in tipo]
    return [str(tipo)] if tipo else []


def _recorrer(objeto: Any) -> Iterator[dict]:
    """Recorre JSON-LD anidado (@graph, listas, mainEntity...) buscando ClaimReview."""
    if isinstance(objeto, list):
        for item in objeto:
            yield from _recorrer(item)
    elif isinstance(objeto, dict):
        if any(t.split("/")[-1] == "ClaimReview" for t in _tipos(objeto)):
            yield objeto
            return
        for valor in objeto.values():
            if isinstance(valor, (dict, list)):
                yield from _recorrer(valor)


def _cargar_json(bloque: str) -> Any:
    bloque = bloque.strip()
    if bloque.startswith("<!--"):
        bloque = bloque[4:]
    if bloque.endswith("-->"):
        bloque = bloque[:-3]
    try:
        return json.loads(bloque, strict=False)
    except json.JSONDecodeError:
        # Errores comunes: comas sobrantes antes de } o ].
        try:
            return json.loads(re.sub(r",\s*([}\]])", r"\1", bloque), strict=False)
        except json.JSONDecodeError:
            return None


def extraer_de_html(html: bytes | str, url_pagina: str = "") -> list[dict]:
    """Devuelve los ClaimReview (normalizados) que haya en una página HTML."""
    from lxml import html as lxml_html

    if not html:
        return []
    if isinstance(html, bytes):
        # Sin charset declarado lxml asumiría Latin-1; se prueba UTF-8 primero.
        try:
            html = html.decode("utf-8")
        except UnicodeDecodeError:
            html = html.decode("cp1252", errors="replace")
    try:
        arbol = lxml_html.fromstring(html)
    except ValueError:  # texto con declaración XML: lxml exige bytes
        try:
            arbol = lxml_html.fromstring(html.encode("utf-8"))
        except Exception:  # noqa: BLE001
            return []
    except Exception:  # noqa: BLE001 - HTML roto
        return []
    resultados = []
    for script in arbol.xpath('//script[contains(@type, "ld+json")]'):
        datos = _cargar_json(script.text_content() or "")
        if datos is None:
            continue
        for cr in _recorrer(datos):
            normalizado = normalizar(cr, url_pagina)
            if normalizado:
                resultados.append(normalizado)
    return resultados


def _primero(valor: Any) -> Any:
    if isinstance(valor, list):
        return valor[0] if valor else None
    return valor


def _nombre(valor: Any) -> str:
    valor = _primero(valor)
    if isinstance(valor, dict):
        return str(valor.get("name") or "").strip()
    return str(valor or "").strip()


def _url(valor: Any) -> str:
    valor = _primero(valor)
    if isinstance(valor, dict):
        return str(valor.get("url") or valor.get("@id") or "").strip()
    return str(valor or "").strip() if isinstance(valor, str) and valor.startswith("http") else ""


def normalizar(cr: dict, url_pagina: str = "") -> dict | None:
    """Convierte un ClaimReview en un diccionario simple."""
    if not isinstance(cr, dict):
        return None
    rating = _primero(cr.get("reviewRating")) or {}
    if not isinstance(rating, dict):
        rating = {}
    afirmacion = str(cr.get("claimReviewed") or "").strip()
    item = _primero(cr.get("itemReviewed")) or {}
    if not isinstance(item, dict):
        item = {}
    if not afirmacion:
        afirmacion = str(item.get("name") or "").strip()
    veredicto = str(rating.get("alternateName") or rating.get("name") or "").strip()
    url = str(cr.get("url") or "").strip() or url_pagina
    if not afirmacion and not veredicto:
        return None
    autor = cr.get("author")
    apariciones = []
    for aparicion in item.get("appearance") or item.get("firstAppearance") or []:
        enlace = _url(aparicion)
        if enlace:
            apariciones.append(enlace)
    organizacion = _nombre(autor) or dominio_de(url)
    return {
        "afirmacion": afirmacion,
        "veredicto": veredicto,
        "valor": rating.get("ratingValue"),
        "mejor": rating.get("bestRating"),
        "peor": rating.get("worstRating"),
        "explicacion": str(rating.get("ratingExplanation") or "").strip(),
        "organizacion": organizacion,
        "url_organizacion": _url(autor),
        "url": url,
        "dominio": dominio_de(url),
        "fecha": fecha_iso(cr.get("datePublished")),
        "autor_afirmacion": _nombre(item.get("author")),
        "fecha_afirmacion": fecha_iso(item.get("datePublished")),
        "apariciones": apariciones[:5],
    }


def con_categoria(verificacion: dict) -> dict:
    """Agrega la categoría y su nombre legible a una verificación."""
    categoria = clasificar_veredicto(
        verificacion.get("veredicto"), verificacion.get("valor"), verificacion.get("mejor"), verificacion.get("peor")
    )
    return {**verificacion, "categoria": categoria, "categoria_nombre": NOMBRES[categoria]}
