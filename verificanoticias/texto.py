"""Utilidades de texto: normalización, idioma, frases y búsqueda de expresiones."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from spacy.lang.en.stop_words import STOP_WORDS as _STOP_EN
from spacy.lang.es.stop_words import STOP_WORDS as _STOP_ES

_RE_NO_ALFANUM = re.compile(r"[^0-9a-z%]+")
_RE_PALABRA = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+(?:['’][A-Za-z]+)?")


def sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, solo letras/números separados por un espacio."""
    texto = sin_tildes((texto or "").lower()).replace("’", "'").replace("'", "")
    return _RE_NO_ALFANUM.sub(" ", texto).strip()


STOPWORDS_ES = frozenset(normalizar(p) for p in _STOP_ES)
STOPWORDS_EN = frozenset(normalizar(p) for p in _STOP_EN)
STOPWORDS = STOPWORDS_ES | STOPWORDS_EN

# Palabras muy frecuentes y exclusivas de cada idioma, para detectar el idioma.
_MARCAS_ES = {"el", "la", "los", "las", "de", "del", "que", "y", "en", "un", "una", "por", "con", "para",
              "es", "se", "su", "al", "lo", "como", "mas", "pero", "sus", "le", "ya", "fue", "este", "esta"}
_MARCAS_EN = {"the", "of", "and", "to", "in", "is", "that", "for", "it", "with", "as", "was", "on", "be",
              "by", "this", "are", "from", "at", "has", "have", "an", "will", "his", "her", "they", "said"}


def detectar_idioma(texto: str) -> str:
    """Devuelve "es" o "en" contando palabras típicas de cada idioma."""
    palabras = normalizar(texto).split()
    es = sum(1 for p in palabras if p in _MARCAS_ES)
    en = sum(1 for p in palabras if p in _MARCAS_EN)
    return "en" if en > es else "es"


def palabras(texto: str) -> list[str]:
    return _RE_PALABRA.findall(texto or "")


def palabras_contenido(texto: str, minimo: int = 3) -> list[str]:
    """Palabras normalizadas sin las vacías ("el", "de", "the"...)."""
    return [p for p in normalizar(texto).split() if len(p) >= minimo and p not in STOPWORDS]


def raiz(palabra: str, largo: int = 6) -> str:
    """Raíz aproximada: los primeros caracteres (murió/muere/muerte → muer...)."""
    return palabra[:largo]


_ABREVIATURAS = {"sr", "sra", "srta", "dr", "dra", "lic", "ing", "prof", "etc", "ee", "uu", "eeuu", "mr", "mrs",
                 "ms", "st", "vs", "jr", "inc", "ltd", "co", "no", "nro", "núm", "art", "pág", "aprox", "gral",
                 "u.s", "e.g", "i.e"}
_RE_FIN_FRASE = re.compile(r"(?<=[.!?…])[\"”»']?\s+(?=[\"“«¿¡(]?[A-ZÁÉÍÓÚÑÜ0-9])")


def dividir_frases(texto: str) -> list[str]:
    """Divide un texto en frases (heurística sencilla, sin modelos)."""
    frases: list[str] = []
    for parrafo in re.split(r"\n+", texto or ""):
        parrafo = parrafo.strip()
        if not parrafo:
            continue
        partes = _RE_FIN_FRASE.split(parrafo)
        actual = ""
        for parte in partes:
            actual = f"{actual} {parte}".strip() if actual else parte.strip()
            ultima = actual.rstrip(".!?…\"”»'").split()[-1:] if actual else []
            if ultima and ultima[0].lower().rstrip(".") in _ABREVIATURAS and actual.endswith("."):
                continue  # el punto era de una abreviatura: seguir uniendo
            frases.append(actual)
            actual = ""
        if actual:
            frases.append(actual)
    return [f for f in frases if f]


@lru_cache(maxsize=256)
def _patron(expresiones: tuple[str, ...]) -> re.Pattern | None:
    """Compila una lista de expresiones a una regex sobre texto normalizado.

    Una expresión que termina en ``*`` coincide con cualquier palabra que empiece así.
    """
    partes = []
    for expr in expresiones:
        prefijo = expr.endswith("*")
        norm = normalizar(expr.rstrip("*"))
        if not norm:
            continue
        cuerpo = re.escape(norm).replace(r"\ ", r"\s+")
        partes.append(rf"\b{cuerpo}{'[a-z0-9]*' if prefijo else ''}\b")
    if not partes:
        return None
    # Las más largas primero, para preferir "antes de que lo borren" a "borren".
    partes.sort(key=len, reverse=True)
    return re.compile("|".join(partes))


def buscar_expresiones(texto: str, expresiones: list[str]) -> list[str]:
    """Expresiones de la lista que aparecen en el texto (sin repetir, en orden)."""
    patron = _patron(tuple(expresiones or ()))
    if patron is None:
        return []
    encontradas: list[str] = []
    for m in patron.finditer(normalizar(texto)):
        if m.group(0) not in encontradas:
            encontradas.append(m.group(0))
    return encontradas


def recortar(texto: str, largo: int) -> str:
    texto = (texto or "").strip()
    if len(texto) <= largo:
        return texto
    corte = texto[:largo].rsplit(" ", 1)[0]
    return corte + "…"


_VARIANTES = {"a": "aáàäâ", "e": "eéèëê", "i": "iíìïî", "o": "oóòöô", "u": "uúùüû", "n": "nñ", "c": "cç"}


def quitar_expresiones(contenido: str, expresiones: list[str]) -> str:
    """Quita del texto original las expresiones de la lista (sin importar tildes ni mayúsculas)."""
    for expresion in sorted(expresiones or [], key=len, reverse=True):
        norm = normalizar(expresion.rstrip("*"))
        if not norm:
            continue
        patron = "".join(
            r"\s+" if c == " " else (f"[{_VARIANTES[c]}]" if c in _VARIANTES else re.escape(c)) for c in norm
        )
        contenido = re.sub(rf"(?<!\w){patron}(?!\w)", " ", contenido, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", contenido).strip(" ,.;:")
