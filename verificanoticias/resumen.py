"""Línea de tiempo y resumen extractivo (TextRank con la librería sumy)."""

from __future__ import annotations

from . import similitud, texto
from .fuentes.base import a_datetime


class _Tokenizador:
    """Tokenizador propio para sumy (evita descargar datos de NLTK)."""

    def __init__(self, idioma: str) -> None:
        self.language = "spanish" if idioma == "es" else "english"

    def to_sentences(self, parrafo: str) -> tuple[str, ...]:
        return tuple(texto.dividir_frases(parrafo))

    def to_words(self, frase: str) -> tuple[str, ...]:
        return tuple(texto.palabras(frase))


def linea_de_tiempo(articulos: list[dict]) -> list[dict]:
    """Artículos ordenados del más antiguo al más reciente (sin fecha, al final)."""
    con_fecha = [a for a in articulos if a_datetime(a.get("fecha"))]
    sin_fecha = [a for a in articulos if not a_datetime(a.get("fecha"))]
    con_fecha.sort(key=lambda a: a_datetime(a["fecha"]))
    return [
        {k: a.get(k) for k in ("titulo", "url", "medio", "dominio", "fecha", "categoria", "fuente_busqueda", "similitud")}
        for a in con_fecha + sin_fecha
    ]


def _frases_validas(contenido: str) -> list[str]:
    frases = []
    for frase in texto.dividir_frases(contenido):
        frase = frase.strip()
        palabras = frase.split()
        if 8 <= len(palabras) <= 60 and not frase.endswith(":") and "©" not in frase and "http" not in frase:
            frases.append(frase)
    return frases


def resumen_extractivo(documentos: list[dict], referencia: str, idioma: str, cantidad: int = 5) -> list[dict]:
    """Elige las frases más representativas de varios artículos.

    ``documentos``: ``[{"texto", "url", "medio"}]``. Cada frase del resumen se devuelve
    con el link del artículo del que sale. No se escribe nada nuevo: solo se eligen frases.
    """
    from sumy.models.dom import ObjectDocumentModel, Paragraph, Sentence
    from sumy.nlp.stemmers import Stemmer
    from sumy.summarizers.text_rank import TextRankSummarizer
    from sumy.utils import get_stop_words

    tokenizador = _Tokenizador(idioma)
    origen: dict[str, dict] = {}
    parrafos = []
    for doc in documentos:
        frases = _frases_validas(doc.get("texto", ""))[:40]
        if not frases:
            continue
        # Solo frases relacionadas con la noticia (evita publicidad o notas al pie).
        relevancias = similitud.similitudes(referencia, frases) if referencia else [1.0] * len(frases)
        elegidas = [f for f, r in zip(frases, relevancias) if r >= 0.08]
        for frase in elegidas:
            origen.setdefault(frase, doc)
        if elegidas:
            parrafos.append(Paragraph([Sentence(f, tokenizador) for f in elegidas]))
    if not parrafos:
        return []
    idioma_sumy = tokenizador.language
    resumidor = TextRankSummarizer(Stemmer(idioma_sumy))
    resumidor.stop_words = get_stop_words(idioma_sumy)
    try:
        elegidas = resumidor(ObjectDocumentModel(parrafos), cantidad * 2)
    except Exception:  # noqa: BLE001 - si TextRank falla (texto mínimo), no hay resumen
        return []
    resultado: list[dict] = []
    for oracion in elegidas:
        frase = str(oracion)
        if any(similitud.similitud(frase, r["frase"]) > 0.6 for r in resultado):
            continue  # evitar frases casi repetidas de distintos medios
        doc = origen.get(frase, {})
        resultado.append({"frase": frase, "url": doc.get("url", ""), "medio": doc.get("medio", "")})
        if len(resultado) >= cantidad:
            break
    return resultado
