"""Ajustes para usar la aplicación dentro de GitHub Codespaces (sin instalar nada en tu PC)."""

from __future__ import annotations

import os


def activo() -> bool:
    return os.environ.get("CODESPACES") == "true" and bool(os.environ.get("CODESPACE_NAME"))


def _dominio() -> str:
    return os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN") or "app.github.dev"


def url(puerto: int) -> str | None:
    """Dirección privada con la que GitHub publica el puerto (solo funciona con tu sesión de GitHub)."""
    if not activo():
        return None
    return f"https://{os.environ['CODESPACE_NAME']}-{puerto}.{_dominio()}"


def hosts(puerto_inicial: int, cantidad: int = 20) -> list[str]:
    """Nombres de host que el servidor debe aceptar dentro de este codespace (y de ningún otro)."""
    if not activo():
        return []
    return [f"{os.environ['CODESPACE_NAME']}-{p}.{_dominio()}" for p in range(puerto_inicial, puerto_inicial + cantidad)]
