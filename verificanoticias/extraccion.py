"""Lectura de la entrada: texto pegado, titular o URL (con trafilatura)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from urllib.parse import unquote, urlparse

from . import red, texto
from .fuentes import claimreview
from .fuentes.base import dominio_de, fecha_iso

_RE_URL = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)


@dataclass
class Noticia:
    tipo: str                    # "url" o "texto"
    titulo: str = ""
    cuerpo: str = ""
    url: str = ""
    dominio: str = ""
    autor: str = ""
    fecha: str | None = None     # ISO 8601
    sitio: str = ""
    idioma: str = "es"
    error_descarga: str | None = None
    tipo_error: str | None = None
    claimreviews_en_pagina: list[dict] = field(default_factory=list)

    @property
    def tiene_texto(self) -> bool:
        return bool(self.cuerpo.strip())

    def texto_completo(self) -> str:
        return f"{self.titulo}\n{self.cuerpo}".strip()

    def referencia(self, titulo: str | None = None, max_caracteres: int = 400) -> str:
        """Titular + comienzo del texto: lo que se compara con otros artículos."""
        inicio = " ".join(texto.dividir_frases(self.cuerpo)[:2]) if self.cuerpo else ""
        return f"{titulo if titulo is not None else self.titulo}. {texto.recortar(inicio, max_caracteres)}".strip(". ")

    def a_dict(self) -> dict:
        datos = asdict(self)
        datos["cuerpo_extracto"] = texto.recortar(self.cuerpo, 700)
        datos.pop("cuerpo")
        datos["caracteres"] = len(self.cuerpo)
        return datos


def es_url(entrada: str) -> bool:
    return bool(_RE_URL.match(entrada.strip()))


def normalizar_url(entrada: str) -> str:
    url = entrada.strip()
    if url.lower().startswith("www."):
        url = "https://" + url
    return url


def desde_texto(entrada: str) -> Noticia:
    """Separa titular y cuerpo de un texto pegado."""
    lineas = [l.strip() for l in entrada.strip().splitlines() if l.strip()]
    if not lineas:
        return Noticia(tipo="texto")
    if len(lineas) > 1 and len(lineas[0]) <= 300:
        titulo, cuerpo = lineas[0], "\n".join(lineas[1:])
    else:
        frases = texto.dividir_frases(lineas[0])
        if len(lineas) == 1 and len(lineas[0]) <= 300:
            titulo, cuerpo = lineas[0], ""
        else:
            titulo = frases[0] if frases else lineas[0][:300]
            cuerpo = "\n".join(lineas)
    noticia = Noticia(tipo="texto", titulo=titulo, cuerpo=cuerpo)
    noticia.idioma = texto.detectar_idioma(noticia.texto_completo())
    return noticia


def _titulo_desde_url(url: str) -> str:
    """Si no se puede descargar la página, se usa el "slug" de la dirección como titular."""
    ruta = unquote(urlparse(url).path)
    segmentos = [s for s in ruta.split("/") if s]
    mejor = max(segmentos, key=lambda s: s.count("-") + s.count("_"), default="")
    mejor = re.sub(r"\.(html?|php|aspx?)$", "", mejor)
    # Se descartan identificadores (n123456, 9f8e7d6c5b) pero no números cortos como "88".
    palabras = [p for p in re.split(r"[-_]+", mejor)
                if p and not re.fullmatch(r"(?=.*\d)[0-9a-f]{8,}|\d{5,}|[a-z]\d{4,}", p, re.I)]
    return " ".join(palabras) if len(palabras) >= 3 else ""


def desde_url(entrada: str) -> Noticia:
    url = normalizar_url(entrada)
    noticia = Noticia(tipo="url", url=url, dominio=dominio_de(url))
    if urlparse(url).scheme not in ("http", "https"):
        noticia.error_descarga = "Solo se aceptan direcciones que empiecen con http:// o https://"
        noticia.tipo_error = red.ERROR
        return noticia
    try:
        respuesta = red.obtener(url, tipo="navegador")
    except red.ErrorRed as e:
        noticia.error_descarga = e.mensaje
        noticia.tipo_error = e.tipo
        noticia.titulo = _titulo_desde_url(url)
        noticia.idioma = texto.detectar_idioma(noticia.titulo)
        return noticia

    noticia.url = respuesta.url
    noticia.dominio = dominio_de(respuesta.url)
    noticia.claimreviews_en_pagina = claimreview.extraer_de_html(respuesta.content, respuesta.url)

    import trafilatura

    try:
        documento = trafilatura.bare_extraction(respuesta.content, url=respuesta.url, with_metadata=True)
    except Exception:  # noqa: BLE001 - trafilatura puede fallar con HTML muy roto
        documento = None
    datos = documento.as_dict() if hasattr(documento, "as_dict") else (documento or {})
    noticia.titulo = (datos.get("title") or "").strip() or _titulo_desde_url(url)
    cuerpo = (datos.get("text") or "").strip()
    # trafilatura a veces repite el titular como primera línea del texto
    if cuerpo.startswith(noticia.titulo):
        cuerpo = cuerpo[len(noticia.titulo):].strip()
    noticia.cuerpo = cuerpo
    noticia.autor = (datos.get("author") or "").strip()
    noticia.fecha = fecha_iso(datos.get("date"))
    noticia.sitio = (datos.get("sitename") or "").strip()
    noticia.idioma = texto.detectar_idioma(noticia.texto_completo())
    if not noticia.cuerpo:
        noticia.error_descarga = (
            "Se descargó la página pero no se pudo extraer el texto de la noticia "
            "(puede requerir suscripción o cargarse con JavaScript). Puedes pegar el texto directamente."
        )
        noticia.tipo_error = "sin_texto"
    return noticia


def leer(entrada: str) -> Noticia:
    return desde_url(entrada) if es_url(entrada) else desde_texto(entrada)
