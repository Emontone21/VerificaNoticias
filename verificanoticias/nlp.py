"""Palabras clave (YAKE) y nombres propios (spaCy, modelos pequeños) para armar las búsquedas."""

from __future__ import annotations

import re
import threading
from collections import Counter

from . import texto

MODELOS = {"es": "es_core_news_sm", "en": "en_core_web_sm"}
TIPOS = {
    "PER": "persona", "PERSON": "persona",
    "LOC": "lugar", "GPE": "lugar", "FAC": "lugar",
    "ORG": "organización",
}
# Palabras que se quitan del titular antes de buscarlo (no aportan al tema).
_RUIDO_TITULAR = ["urgente", "ultimo momento", "atencion", "breaking", "breaking news", "video", "fotos",
                  "en vivo", "exclusivo", "impactante", "increible", "mira", "mire", "miren", "viral", "ojo"]
# Palabras demasiado generales para restringir una búsqueda.
_GENERICAS = {"ano", "anos", "dia", "dias", "hoy", "ayer", "manana", "semana", "mes", "meses", "hora", "horas",
              "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo", "millones", "miles",
              "personas", "gente", "caso", "casos", "pais", "parte", "forma", "vez", "nuevo", "nueva", "nuevos",
              "year", "years", "day", "days", "today", "yesterday", "week", "month", "people", "new", "says",
              "said", "time", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
              "million", "millions", "according", "video", "foto", "fotos", "photo", "photos"}
_ARTICULOS_INICIALES = re.compile(r"^(el|la|los|las|the|un|una|a|an)\s+", re.IGNORECASE)

_modelos: dict = {}
_errores_modelo: dict = {}
_lock = threading.Lock()


def modelo(idioma: str):
    """Carga (una sola vez) el modelo pequeño de spaCy del idioma. ``None`` si no está instalado."""
    nombre = MODELOS.get(idioma, MODELOS["es"])
    with _lock:
        if nombre in _modelos:
            return _modelos[nombre]
        try:
            import spacy

            _modelos[nombre] = spacy.load(nombre, exclude=["parser", "lemmatizer", "senter"])
        except Exception as e:  # noqa: BLE001 - modelo ausente o dañado: se usa una heurística
            _modelos[nombre] = None
            _errores_modelo[nombre] = str(e)
        return _modelos[nombre]


def precargar() -> None:
    for idioma in MODELOS:
        modelo(idioma)


def _limpiar_entidad(valor: str) -> str:
    valor = re.sub(r"\s+", " ", valor.strip(" \n\t\"'“”«»‘’.,;:()[]"))
    return _ARTICULOS_INICIALES.sub("", valor)


def _entidades_heuristicas(contenido: str) -> list[tuple[str, str]]:
    """Sin modelo: secuencias de palabras con mayúscula que no inician una frase."""
    encontradas = []
    for frase in texto.dividir_frases(contenido):
        palabras = frase.split()
        actual: list[str] = []
        for i, palabra in enumerate(palabras):
            limpia = palabra.strip(".,;:!?¡¿\"'()«»“”")
            if i > 0 and limpia[:1].isupper() and not limpia.isupper() and len(limpia) > 1:
                actual.append(limpia)
            else:
                if len(actual) >= 1:
                    encontradas.append((" ".join(actual), "organización" if len(actual) > 2 else "persona"))
                actual = []
        if actual:
            encontradas.append((" ".join(actual), "persona"))
    return encontradas


def entidades(titulo: str, cuerpo: str, idioma: str) -> list[dict]:
    """Personas, lugares y organizaciones mencionadas, de más a menos importantes."""
    contenido = f"{titulo}.\n{cuerpo[:6000]}"
    nlp = modelo(idioma)
    if nlp is not None:
        doc = nlp(contenido)
        pares = [(e.text, TIPOS[e.label_]) for e in doc.ents if e.label_ in TIPOS]
    else:
        pares = _entidades_heuristicas(contenido)
    conteo: Counter = Counter()
    tipos: dict[str, Counter] = {}
    formas: dict[str, str] = {}
    for valor, tipo in pares:
        limpio = _limpiar_entidad(valor)
        clave = texto.normalizar(limpio)
        if len(clave) < 3 or clave.isdigit() or all(p in texto.STOPWORDS for p in clave.split()):
            continue
        conteo[clave] += 1
        tipos.setdefault(clave, Counter())[tipo] += 1
        if clave not in formas or len(limpio) > len(formas[clave]):
            formas[clave] = limpio
    # Unir "Milei" con "Javier Milei": la forma corta suma a la larga.
    for corta in list(conteo):
        for larga in list(conteo):
            if corta != larga and corta in conteo and larga in conteo and f" {corta} " in f" {larga} ":
                conteo[larga] += conteo.pop(corta)
                break
    titulo_norm = f" {texto.normalizar(titulo)} "
    resultado = []
    for clave, menciones in conteo.items():
        en_titulo = any(f" {p} " in titulo_norm for p in clave.split() if len(p) > 3) or f" {clave} " in titulo_norm
        resultado.append({
            "texto": formas[clave],
            "tipo": tipos[clave].most_common(1)[0][0] if clave in tipos else "persona",
            "menciones": menciones,
            "en_titulo": en_titulo,
        })
    resultado.sort(key=lambda e: (not e["en_titulo"], -e["menciones"]))
    return resultado[:12]


def palabras_clave(contenido: str, idioma: str, cantidad: int = 10, n: int = 2) -> list[str]:
    """Palabras clave con YAKE (estadístico, sin modelos). ``n``: palabras por expresión."""
    contenido = contenido.strip()
    if not contenido:
        return []
    try:
        import yake

        extractor = yake.KeywordExtractor(lan="es" if idioma == "es" else "en", n=n, top=cantidad * 2, dedupLim=0.7)
        candidatas = [k for k, _ in extractor.extract_keywords(contenido[:5000])]
    except Exception:  # noqa: BLE001 - si YAKE falla, frecuencia simple
        candidatas = [p for p, _ in Counter(texto.palabras_contenido(contenido, 4)).most_common(cantidad * 2)]
    resultado: list[str] = []
    for k in candidatas:
        norm = texto.normalizar(k)
        palabras = norm.split()
        if not palabras or all(p in texto.STOPWORDS or p in _GENERICAS or len(p) < 3 for p in palabras):
            continue
        if any(norm in texto.normalizar(r) or texto.normalizar(r) in norm for r in resultado):
            continue
        resultado.append(k)
        if len(resultado) >= cantidad:
            break
    return resultado


def limpiar_titular(titulo: str, max_palabras: int = 14) -> str:
    """Titular sin signos de alarma ni palabras de relleno, para buscarlo."""
    limpio = re.sub(r"[!¡?¿\"“”«»#*|]+", " ", titulo)
    limpio = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]+", " ", limpio)  # emojis
    palabras: list[str] = []
    for palabra in limpio.split():
        palabra = palabra.strip(":;,.")
        if not palabra or texto.normalizar(palabra) in _RUIDO_TITULAR:
            continue
        if palabra.isupper() and len(palabra) > 4:
            palabra = palabra.capitalize()
        palabras.append(palabra)
    return " ".join(palabras[:max_palabras])


def _categorias_gramaticales(contenido: str, idioma: str) -> dict[str, str]:
    """Categoría gramatical (sustantivo, verbo...) de cada palabra, si hay modelo."""
    nlp = modelo(idioma)
    if nlp is None or not contenido:
        return {}
    return {texto.normalizar(t.text): t.pos_ for t in nlp(contenido) if t.pos_}


def _comillas(termino: str) -> str:
    return f'"{termino}"' if " " in termino else termino


def preparar(titulo: str, cuerpo: str, idioma: str) -> dict:
    """Términos y consultas que se usan en las búsquedas."""
    ents = entidades(titulo, cuerpo, idioma)
    clave_titulo = palabras_clave(limpiar_titular(titulo), idioma, 6)
    clave_cuerpo = palabras_clave(cuerpo, idioma, 8) if cuerpo else []

    terminos: list[str] = []

    def agregar(valor: str) -> None:
        norm = texto.normalizar(valor)
        if not norm or norm in texto.STOPWORDS:
            return
        for existente in terminos:
            e = texto.normalizar(existente)
            if norm == e or f" {norm} " in f" {e} ":
                return
        terminos.append(valor)

    for e in ents:
        if e["en_titulo"]:
            agregar(e["texto"])
    for k in clave_titulo:
        agregar(k)
    for e in ents:
        agregar(e["texto"])
    for k in clave_cuerpo:
        agregar(k)

    # Consulta principal: hasta 2 nombres propios + palabras sueltas importantes del titular
    # (primero sustantivos, después verbos y el resto).
    principales: list[str] = [e["texto"] for e in ents if e["en_titulo"]][:2]
    categorias = _categorias_gramaticales(limpiar_titular(titulo), idioma)
    sueltas = palabras_clave(limpiar_titular(titulo), idioma, 8, n=1)
    sueltas.sort(key=lambda k: 0 if categorias.get(texto.normalizar(k)) in ("NOUN", "PROPN") else 1)
    sustantivos: list[str] = []
    for k in sueltas:
        nk = texto.normalizar(k)
        if nk in _GENERICAS or any(nk in texto.normalizar(p).split() for p in principales):
            continue
        if categorias.get(nk) in ("NOUN", "PROPN"):
            sustantivos.append(k)
        if len(principales) < 4:
            principales.append(k)
    if not principales:
        principales = terminos[:4]
    entidades_principales = [e["texto"] for e in ents[:2]] or sustantivos[:2] or terminos[:2]
    return {
        "idioma": idioma,
        "entidades": ents,
        "palabras_clave": list(dict.fromkeys(clave_titulo + clave_cuerpo))[:12],
        "terminos": terminos[:14],
        "terminos_consulta": principales,
        "terminos_amplios": entidades_principales[:2],
        "consulta": " ".join(_comillas(t) for t in principales),
        "consulta_amplia": " ".join(_comillas(t) for t in entidades_principales[:2]),
        "consulta_titular": limpiar_titular(titulo),
        "modelo_entidades": MODELOS.get(idioma) if modelo(idioma) is not None else "heurística (modelo no disponible)",
    }
