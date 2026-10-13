"""Acceso a internet con errores claros en español."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from . import config

# Tipos de error que entiende la interfaz.
SIN_INTERNET = "sin_internet"
SIN_CONEXION_SITIO = "sin_conexion_sitio"
TIMEOUT = "timeout"
LIMITE = "limite"
BLOQUEADO = "bloqueado"
NO_ENCONTRADO = "no_encontrado"
SERVIDOR = "servidor"
RESPUESTA_INVALIDA = "respuesta_invalida"
ERROR = "error"

MENSAJES = {
    SIN_INTERNET: "No hay conexión a internet.",
    SIN_CONEXION_SITIO: "No se pudo conectar con el sitio.",
    TIMEOUT: "El sitio tardó demasiado en responder.",
    LIMITE: "Se alcanzó el límite de consultas. Espera unos minutos y vuelve a intentar.",
    BLOQUEADO: "El sitio bloqueó la descarga.",
    NO_ENCONTRADO: "La página no existe (error 404).",
    SERVIDOR: "El sitio tuvo un error interno.",
    RESPUESTA_INVALIDA: "El sitio respondió algo que no se pudo interpretar.",
    ERROR: "Error inesperado al consultar el sitio.",
}


class ErrorRed(Exception):
    """Error al consultar un sitio, con un tipo y un mensaje para el usuario."""

    def __init__(self, tipo: str, mensaje: str | None = None, url: str | None = None):
        self.tipo = tipo
        self.url = url
        self.mensaje = mensaje or MENSAJES.get(tipo, MENSAJES[ERROR])
        super().__init__(self.mensaje)


@dataclass
class Respuesta:
    """Respuesta descargada (el contenido puede estar recortado al tamaño máximo)."""

    url: str
    status_code: int
    headers: httpx.Headers
    content: bytes
    encoding: str | None = None

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8", errors="replace")

    def json(self):
        return json.loads(self.text, strict=False)


def usar_certificados_del_sistema() -> None:
    """Usa los certificados de Windows/macOS en lugar de la lista incluida en Python.

    Evita errores de certificado cuando un antivirus o una red corporativa inspecciona HTTPS.
    """
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001 - si no está disponible, se usan los certificados de Python
        pass


_clientes: dict[str, httpx.Client] = {}
_clientes_lock = threading.Lock()


def _cliente(tipo: str) -> httpx.Client:
    """Cliente HTTP compartido. ``tipo`` es "api" o "navegador"."""
    with _clientes_lock:
        if tipo not in _clientes:
            cfg = config.obtener()
            if tipo == "navegador":
                headers = {
                    "User-Agent": config.valor(cfg, "red.user_agent_navegador"),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "es-419,es;q=0.9,en;q=0.8",
                }
            else:
                headers = {"User-Agent": config.valor(cfg, "red.user_agent_apis")}
            _clientes[tipo] = httpx.Client(
                headers=headers,
                follow_redirects=True,
                timeout=httpx.Timeout(config.valor(cfg, "red.timeout_segundos", 15), connect=8),
            )
        return _clientes[tipo]


def cerrar_clientes() -> None:
    with _clientes_lock:
        for c in _clientes.values():
            c.close()
        _clientes.clear()


def _host(url: str) -> str:
    return urlparse(url).hostname or url


def _error_por_estado(respuesta: Respuesta) -> ErrorRed | None:
    codigo = respuesta.status_code
    url = str(respuesta.url)
    host = _host(url)
    if codigo == 429:
        return ErrorRed(LIMITE, f"{host} limitó las consultas (error 429). Espera unos minutos.", url)
    if codigo in (401, 403, 451):
        return ErrorRed(BLOQUEADO, f"{host} bloqueó la descarga (error {codigo}).", url)
    if codigo in (404, 410):
        return ErrorRed(NO_ENCONTRADO, f"{host}: la página no existe (error {codigo}).", url)
    if codigo >= 500:
        return ErrorRed(SERVIDOR, f"{host} tuvo un error interno (error {codigo}).", url)
    if codigo >= 400:
        return ErrorRed(ERROR, f"{host} respondió con error {codigo}.", url)
    return None


def obtener(
    url: str,
    params: dict | None = None,
    tipo: str = "api",
    max_bytes: int | None = None,
    aceptar_404: bool = False,
) -> Respuesta:
    """Descarga una URL. Lanza ``ErrorRed`` con un mensaje claro si falla."""
    cfg = config.obtener()
    if max_bytes is None:
        max_bytes = int(float(config.valor(cfg, "red.max_megabytes_por_pagina", 5)) * 1024 * 1024)
    host = _host(url)
    try:
        with _cliente(tipo).stream("GET", url, params=params) as r:
            partes = []
            total = 0
            for parte in r.iter_bytes():
                partes.append(parte)
                total += len(parte)
                if total > max_bytes:
                    break
            respuesta = Respuesta(
                url=str(r.url),
                status_code=r.status_code,
                headers=r.headers,
                content=b"".join(partes),
                encoding=r.charset_encoding,
            )
    except httpx.TimeoutException as e:
        raise ErrorRed(TIMEOUT, f"{host} tardó demasiado en responder.", url) from e
    except (httpx.ConnectError, httpx.ProxyError) as e:
        if not hay_internet():
            raise ErrorRed(SIN_INTERNET, url=url) from e
        raise ErrorRed(SIN_CONEXION_SITIO, f"No se pudo conectar con {host}.", url) from e
    except httpx.HTTPError as e:
        raise ErrorRed(ERROR, f"Error al consultar {host}: {type(e).__name__}.", url) from e
    if aceptar_404 and respuesta.status_code == 404:
        return respuesta
    error = _error_por_estado(respuesta)
    if error:
        raise error
    return respuesta


_internet = {"valor": None, "momento": 0.0}
_internet_lock = threading.Lock()


def hay_internet(forzar: bool = False) -> bool:
    """Comprueba si hay conexión (el resultado se recuerda 30 segundos)."""
    with _internet_lock:
        if not forzar and _internet["valor"] is not None and time.time() - _internet["momento"] < 30:
            return _internet["valor"]
        sitios = config.valor(config.obtener(), "red.sitios_prueba_internet", []) or []
        resultado = False
        for sitio in sitios:
            try:
                httpx.head(sitio, timeout=4, follow_redirects=False)
                resultado = True
                break
            except httpx.HTTPError:
                continue
        _internet["valor"] = resultado
        _internet["momento"] = time.time()
        return resultado


def reiniciar_estado_internet() -> None:
    with _internet_lock:
        _internet["valor"] = None
        _internet["momento"] = 0.0


def descargar_archivo(url: str, destino, progreso=None, timeout: float = 60) -> int:
    """Descarga un archivo grande a disco mostrando el avance. Devuelve los bytes descargados.

    ``progreso(bytes_descargados, bytes_totales_o_None)`` se llama cada tanto.
    """
    host = _host(url)
    descargados = 0
    try:
        with _cliente("api").stream("GET", url, timeout=httpx.Timeout(timeout, connect=10)) as r:
            error = _error_por_estado(
                Respuesta(url=str(r.url), status_code=r.status_code, headers=r.headers, content=b"")
            )
            if error:
                raise error
            total = int(r.headers.get("content-length") or 0) or None
            with open(destino, "wb") as f:
                for parte in r.iter_bytes(chunk_size=1024 * 256):
                    f.write(parte)
                    descargados += len(parte)
                    if progreso:
                        progreso(descargados, total)
    except httpx.TimeoutException as e:
        raise ErrorRed(TIMEOUT, f"{host} tardó demasiado en responder.", url) from e
    except (httpx.ConnectError, httpx.ProxyError) as e:
        if not hay_internet():
            raise ErrorRed(SIN_INTERNET, url=url) from e
        raise ErrorRed(SIN_CONEXION_SITIO, f"No se pudo conectar con {host}.", url) from e
    except httpx.HTTPError as e:
        raise ErrorRed(ERROR, f"La descarga desde {host} se interrumpió ({type(e).__name__}).", url) from e
    return descargados
