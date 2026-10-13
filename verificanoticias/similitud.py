"""Similitud de textos con TF-IDF (scikit-learn), sin modelos de IA.

Se combinan dos vistas del texto:
- palabras recortadas a sus primeras 5 letras (y pares de ellas), para medir
  si hablan de lo mismo tolerando plurales y conjugaciones (vacuna/vacunas);
- fragmentos de 3 a 5 letras, para tolerar otras variaciones (murió/muere).
El resultado va de 0 (nada en común) a 1 (textos iguales).
"""

from __future__ import annotations

import warnings

from . import texto


def preparar(contenido: str) -> str:
    return " ".join(texto.raiz(p, 5) for p in texto.palabras_contenido(contenido, minimo=2))


def similitudes(referencia: str, textos: list[str]) -> list[float]:
    """Similitud de cada texto con la referencia."""
    if not textos:
        return []
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    documentos = [preparar(referencia)] + [preparar(t) for t in textos]
    if not documentos[0].strip():
        return [0.0] * len(textos)
    puntajes = []
    for opciones in (
        {"analyzer": "word", "ngram_range": (1, 2), "token_pattern": r"(?u)\b\w+\b"},
        {"analyzer": "char_wb", "ngram_range": (3, 5)},
    ):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                matriz = TfidfVectorizer(sublinear_tf=True, **opciones).fit_transform(documentos)
        except ValueError:  # vocabulario vacío
            puntajes.append([0.0] * len(textos))
            continue
        puntajes.append(cosine_similarity(matriz[0:1], matriz[1:])[0].tolist())
    return [round((a + b) / 2, 3) for a, b in zip(*puntajes)]


def similitud(a: str, b: str) -> float:
    return similitudes(a, [b])[0]


def palabras_compartidas(a: str, b: str, maximo: int = 8) -> list[str]:
    """Palabras importantes que aparecen en ambos textos (para mostrar al usuario)."""
    raices_b = {texto.raiz(p, 5) for p in texto.palabras_contenido(b, minimo=3)}
    compartidas: list[str] = []
    for p in texto.palabras_contenido(a, minimo=3):
        if texto.raiz(p, 5) in raices_b and p not in compartidas:
            compartidas.append(p)
        if len(compartidas) >= maximo:
            break
    return compartidas


def cobertura_de_palabras(titulo: str, cuerpo: str) -> float | None:
    """Proporción de palabras del titular que aparecen en el cuerpo (0 a 1)."""
    palabras_titulo = {texto.raiz(p, 5) for p in texto.palabras_contenido(titulo, minimo=4)}
    if len(palabras_titulo) < 2:
        return None
    raices_cuerpo = {texto.raiz(p, 5) for p in texto.palabras_contenido(cuerpo, minimo=4)}
    return round(len(palabras_titulo & raices_cuerpo) / len(palabras_titulo), 2)


def cobertura_ponderada(referencia: str, textos: list[str]) -> list[float]:
    """Qué parte de cada texto aparece en la referencia (0 a 1), dando más peso a las palabras raras.

    Sirve para no confundir "las vacunas causan VIH" con "las vacunas causan infertilidad":
    se parecen mucho, pero la palabra distintiva ("VIH") no está en la noticia.
    """
    if not textos:
        return []
    from sklearn.feature_extraction.text import TfidfVectorizer

    raices = [[texto.raiz(p, 5) for p in texto.palabras_contenido(t, minimo=3)] for t in textos]
    raices_ref = {texto.raiz(p, 5) for p in texto.palabras_contenido(referencia, minimo=3)}
    documentos = [" ".join(r) for r in raices] + [" ".join(sorted(raices_ref))]
    try:
        vectorizador = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b").fit(documentos)
        idf = dict(zip(vectorizador.get_feature_names_out(), vectorizador.idf_))
    except ValueError:
        return [0.0] * len(textos)
    resultado = []
    for r in raices:
        unicas = set(r)
        total = sum(idf.get(p, 1.0) for p in unicas)
        resultado.append(round(sum(idf.get(p, 1.0) for p in unicas & raices_ref) / total, 2) if total else 0.0)
    return resultado
