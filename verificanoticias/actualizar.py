"""Descarga y actualiza los datos públicos: listas de dominios y feed ClaimReview.

Uso desde la consola:  python -m verificanoticias.actualizar [--solo-listas]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
from typing import Callable

from . import config, dominios, red
from .fuentes import indice_claimreview

Progreso = Callable[[str], None]


def _escribir_csv(nombre: str, encabezado: list[str], filas: list[list]) -> None:
    ruta = config.ruta_listas_importadas() / nombre
    temporal = ruta.with_suffix(".tmp")
    with open(temporal, "w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(encabezado)
        escritor.writerows(filas)
    temporal.replace(ruta)


def importar_domain_quality(progreso: Progreso | None = None) -> int:
    opciones = config.valor(config.obtener(), "listas_publicas.domain_quality_ratings", {}) or {}
    if not opciones.get("activa", True):
        return 0
    if progreso:
        progreso("Descargando la lista domain-quality-ratings…")
    respuesta = red.obtener(opciones["url"], max_bytes=30 * 1024 * 1024)
    confiable = float(opciones.get("umbral_confiable", 0.75))
    poco = float(opciones.get("umbral_poco_confiable", 0.25))
    filas = []
    for fila in csv.DictReader(io.StringIO(respuesta.text)):
        try:
            valor = float(fila.get("pc1", ""))
        except ValueError:
            continue
        dominio = (fila.get("domain") or "").strip().lower()
        if not dominio:
            continue
        if valor >= confiable:
            filas.append([dominio, round(valor, 3), dominios.CONFIABLE])
        elif valor <= poco:
            filas.append([dominio, round(valor, 3), dominios.DESINFORMACION])
    if not filas:
        raise red.ErrorRed(red.RESPUESTA_INVALIDA, "La lista domain-quality-ratings llegó vacía o cambió de formato.")
    _escribir_csv("domain_quality.csv", ["dominio", "puntaje", "categoria"], filas)
    return len(filas)


def importar_opensources(progreso: Progreso | None = None) -> int:
    opciones = config.valor(config.obtener(), "listas_publicas.opensources", {}) or {}
    if not opciones.get("activa", True):
        return 0
    if progreso:
        progreso("Descargando la lista OpenSources…")
    datos = red.obtener(opciones["url"], max_bytes=20 * 1024 * 1024).json()
    tipos_desinf = {t.strip().lower() for t in opciones.get("tipos_desinformacion") or []}
    tipos_satira = {t.strip().lower() for t in opciones.get("tipos_satira") or []}
    filas = []
    for dominio, info in (datos or {}).items():
        if not isinstance(info, dict):
            continue
        tipos = [str(info.get(k) or "").strip().lower() for k in ("type", "2nd type", "3rd type")]
        tipos = [t for t in tipos if t]
        if any(t in tipos_satira for t in tipos[:1]):
            categoria = dominios.SATIRA
        elif any(t in tipos_desinf for t in tipos):
            categoria = dominios.DESINFORMACION
        else:
            continue
        filas.append([dominio.strip().lower(), "/".join(tipos), categoria])
    if not filas:
        raise red.ErrorRed(red.RESPUESTA_INVALIDA, "La lista OpenSources llegó vacía o cambió de formato.")
    _escribir_csv("opensources.csv", ["dominio", "tipo", "categoria"], filas)
    return len(filas)


def actualizar_listas(progreso: Progreso | None = None) -> dict:
    resultado: dict = {"errores": []}
    for nombre, funcion in (("domain_quality", importar_domain_quality), ("opensources", importar_opensources)):
        try:
            resultado[nombre] = funcion(progreso)
        except red.ErrorRed as e:
            resultado["errores"].append(f"{nombre}: {e.mensaje}")
        except (ValueError, json.JSONDecodeError) as e:
            resultado["errores"].append(f"{nombre}: formato inesperado ({e})")
    dominios.recargar_listas()
    return resultado


def actualizar_todo(progreso: Progreso | None = None, incluir_feed: bool = True) -> dict:
    inicio = time.time()
    resultado = {"listas": actualizar_listas(progreso)}
    if incluir_feed:
        try:
            resultado["claimreview"] = indice_claimreview.actualizar(progreso)
        except red.ErrorRed as e:
            resultado["claimreview"] = {"error": e.mensaje}
        dominios.recargar_listas()
    resultado["segundos"] = round(time.time() - inicio, 1)
    return resultado


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Actualiza las listas de dominios y la base de verificaciones.")
    parser.add_argument("--solo-listas", action="store_true", help="No descargar el feed ClaimReview (200 MB).")
    args = parser.parse_args(argumentos)
    red.usar_certificados_del_sistema()
    print("Actualizando datos de VerificaNoticias. Esto puede tardar unos minutos.\n")
    ultimo = [""]

    def mostrar(mensaje: str) -> None:
        if mensaje != ultimo[0]:
            print("\r" + mensaje.ljust(70), end="", flush=True)
            ultimo[0] = mensaje

    resultado = actualizar_todo(mostrar, incluir_feed=not args.solo_listas)
    print("\n")
    listas = resultado["listas"]
    if "domain_quality" in listas:
        print(f"  - domain-quality-ratings: {listas['domain_quality']} dominios importados")
    if "opensources" in listas:
        print(f"  - OpenSources: {listas['opensources']} dominios importados")
    for error in listas["errores"]:
        print(f"  ! {error}")
    cr = resultado.get("claimreview")
    if cr:
        if "error" in cr:
            print(f"  ! Base de verificaciones: {cr['error']}")
        else:
            print(f"  - Base de verificaciones: {cr['cantidad']:,} verificaciones".replace(",", "."))
            print(f"  - Verificadores detectados en el feed: {cr['verificadores_detectados']}")
    print(f"\nListo en {resultado['segundos']} segundos.")
    hubo_error = bool(listas["errores"]) or (cr is not None and "error" in cr)
    return 1 if hubo_error else 0


if __name__ == "__main__":
    sys.exit(main())
