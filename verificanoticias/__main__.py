"""Arranque de la aplicación: ``python -m verificanoticias``."""

from __future__ import annotations

import socket
import sys
import threading
import webbrowser


def _puerto_libre(inicial: int) -> int:
    for puerto in range(inicial, inicial + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", puerto))
                return puerto
            except OSError:
                continue
    raise SystemExit(f"No hay puertos libres entre {inicial} y {inicial + 19}.")


def main() -> None:
    from . import config

    try:
        cfg = config.obtener()
    except config.ErrorConfig as e:
        print(f"\nERROR en la configuración: {e}\n")
        input("Presiona Enter para cerrar...")
        sys.exit(1)

    import uvicorn

    from . import codespaces, nlp, red
    from .web.app import app

    red.usar_certificados_del_sistema()

    puerto = _puerto_libre(int(config.valor(cfg, "servidor.puerto", 8000)))
    url = codespaces.url(puerto) or f"http://127.0.0.1:{puerto}"
    print("=" * 60)
    print("  VerificaNoticias está funcionando.")
    print(f"  Abre en tu navegador: {url}")
    if codespaces.activo():
        print("  Si no se abre solo: pestaña PUERTOS, puerto", puerto, "→ ícono del globo.")
        print("  Para apagar la aplicación, presiona Ctrl+C en esta terminal.")
    else:
        print("  Para apagar la aplicación, cierra esta ventana.")
    print("=" * 60)
    # Cargar los modelos de idioma en segundo plano para que el primer análisis sea más rápido.
    threading.Thread(target=nlp.precargar, daemon=True).start()
    if config.valor(cfg, "servidor.abrir_navegador", True):
        # En Codespaces se espera un poco más: GitHub tarda unos segundos en publicar el puerto.
        threading.Timer(4 if codespaces.activo() else 1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=puerto, log_level="warning")


if __name__ == "__main__":
    main()
