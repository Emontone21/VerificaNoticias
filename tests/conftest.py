"""Configuración común de los tests: cada test usa carpetas temporales y nunca sale a internet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from verificanoticias import config, dominios, red

DATOS = Path(__file__).parent / "datos"


@pytest.fixture(autouse=True)
def entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("VERIFICANOTICIAS_DATOS", str(tmp_path / "datos"))
    monkeypatch.setenv("VERIFICANOTICIAS_CONFIG", str(tmp_path / "config.yaml"))
    config.establecer(None)
    dominios._listas = None
    red.reiniciar_estado_internet()

    def sin_red(*args, **kwargs):
        raise AssertionError("Un test intentó salir a internet sin simularlo.")

    monkeypatch.setattr(red, "hay_internet", lambda forzar=False: True)
    monkeypatch.setattr(red, "obtener", sin_red)
    yield tmp_path
    config.establecer(None)
    dominios._listas = None


def leer(nombre: str) -> bytes:
    return (DATOS / nombre).read_bytes()


def respuesta(contenido: bytes | str, url: str = "https://ejemplo.com/", estado: int = 200) -> red.Respuesta:
    import httpx

    if isinstance(contenido, str):
        contenido = contenido.encode("utf-8")
    return red.Respuesta(url=url, status_code=estado, headers=httpx.Headers({}), content=contenido, encoding="utf-8")


def json_fixture(nombre: str):
    return json.loads(leer(nombre))
