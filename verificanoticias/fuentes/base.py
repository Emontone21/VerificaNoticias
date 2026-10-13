"""Estructuras comunes a todas las fuentes de búsqueda."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from .. import red

OK = "ok"
SIN_RESULTADOS = "sin_resultados"
ERROR = "error"
DESACTIVADA = "desactivada"
OMITIDA = "omitida"


@dataclass
class Articulo:
    titulo: str
    url: str
    dominio: str = ""
    fecha: str | None = None        # ISO 8601
    resumen: str = ""
    medio: str = ""
    fuente_busqueda: str = ""        # "GDELT", "Google News", "DuckDuckGo"
    idioma: str | None = None

    def __post_init__(self) -> None:
        if not self.dominio and self.url:
            self.dominio = dominio_de(self.url)

    def a_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultadoFuente:
    nombre: str
    estado: str = OK
    mensaje: str = ""
    tipo_error: str | None = None
    articulos: list[dict] = field(default_factory=list)
    consultas: list[str] = field(default_factory=list)   # URLs realmente consultadas
    desde_cache: bool = False
    duracion: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def respondio(self) -> bool:
        return self.estado in (OK, SIN_RESULTADOS)

    def a_dict(self) -> dict:
        datos = asdict(self)
        datos["cantidad"] = len(self.articulos)
        return datos


def dominio_de(url: str) -> str:
    host = (urlparse(url if "//" in url else f"//{url}").hostname or "").lower()
    for prefijo in ("www.", "m.", "amp.", "mobile."):
        if host.startswith(prefijo):
            host = host[len(prefijo):]
    return host


def fecha_iso(valor: Any) -> str | None:
    """Convierte fechas de distintos formatos a ISO 8601 (UTC si no hay zona)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, time.struct_time):
        return datetime(*valor[:6], tzinfo=timezone.utc).isoformat()
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)
        return valor.isoformat()
    texto = str(valor).strip()
    # Formato de GDELT: 20261013T120000Z
    if len(texto) == 16 and texto[8] == "T" and texto.endswith("Z") and texto[:8].isdigit():
        try:
            return datetime.strptime(texto, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            return None
    try:
        from dateutil import parser as dateparser

        fecha = dateparser.parse(texto)
    except (ValueError, OverflowError, TypeError):
        return None
    if fecha is None or fecha.year < 1990 or fecha.year > 2100:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.isoformat()


def a_datetime(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        fecha = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha


def ejecutar(nombre: str, funcion: Callable[[ResultadoFuente], None]) -> ResultadoFuente:
    """Ejecuta una búsqueda y convierte cualquier error en un estado legible."""
    resultado = ResultadoFuente(nombre=nombre)
    inicio = time.time()
    try:
        funcion(resultado)
        if resultado.estado == OK and not resultado.articulos and not resultado.extra.get("con_datos"):
            resultado.estado = SIN_RESULTADOS
            resultado.mensaje = resultado.mensaje or "La búsqueda no devolvió resultados."
    except red.ErrorRed as e:
        resultado.estado = ERROR
        resultado.tipo_error = e.tipo
        resultado.mensaje = e.mensaje
    except Exception as e:  # noqa: BLE001 - nunca romper el análisis por una fuente
        resultado.estado = ERROR
        resultado.tipo_error = red.ERROR
        resultado.mensaje = f"Error inesperado: {type(e).__name__}: {e}"[:300]
    resultado.duracion = round(time.time() - inicio, 2)
    return resultado
