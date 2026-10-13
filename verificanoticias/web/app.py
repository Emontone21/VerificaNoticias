"""Servidor web local (solo accesible desde esta computadora)."""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__, actualizar, codespaces, config, dominios, historial, pipeline
from ..fuentes import indice_claimreview

ESTATICOS = Path(__file__).resolve().parent / "static"


def hosts_permitidos() -> list[str]:
    """Solo se aceptan pedidos dirigidos a esta computadora (protege contra sitios web maliciosos).

    Dentro de GitHub Codespaces se acepta además la dirección privada de este codespace.
    """
    puerto = int(config.valor(config.obtener(), "servidor.puerto", 8000))
    return ["127.0.0.1", "localhost", "testserver", *codespaces.hosts(puerto)]


app = FastAPI(title="VerificaNoticias", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts_permitidos())
app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")

_trabajos: dict[str, dict] = {}
_trabajos_lock = threading.Lock()
_actualizacion = {"estado": "inactiva", "mensaje": "", "resultado": None, "inicio": None}
_actualizacion_lock = threading.Lock()


class PedidoAnalisis(BaseModel):
    texto: str


class PedidoActualizacion(BaseModel):
    incluir_feed: bool = True


def _registrar_error(contexto: str) -> None:
    try:
        ruta = config.ruta_datos() / "errores.log"
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"\n=== {datetime.now().isoformat()} {contexto}\n{traceback.format_exc()}")
    except OSError:
        pass


def _limpiar_trabajos() -> None:
    limite = time.time() - 3600
    with _trabajos_lock:
        for clave in [k for k, t in _trabajos.items() if t["creado"] < limite and t["estado"] != "en_curso"]:
            _trabajos.pop(clave, None)


@app.get("/")
def inicio() -> FileResponse:
    return FileResponse(ESTATICOS / "index.html")


@app.post("/api/analizar")
def iniciar_analisis(pedido: PedidoAnalisis) -> dict:
    try:
        texto = pipeline.validar_entrada(pedido.texto)
    except pipeline.ErrorAnalisis as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _limpiar_trabajos()
    with _trabajos_lock:
        if any(t["estado"] == "en_curso" for t in _trabajos.values()):
            raise HTTPException(status_code=429, detail="Ya hay un análisis en curso. Espera a que termine.")
        id_trabajo = uuid.uuid4().hex
        trabajo = {"id": id_trabajo, "estado": "en_curso", "creado": time.time(), "resultado": None,
                   "error": None, "progreso": pipeline.Progreso()}
        _trabajos[id_trabajo] = trabajo

    def ejecutar() -> None:
        try:
            trabajo["resultado"] = pipeline.analizar(texto, trabajo["progreso"])
            trabajo["estado"] = "listo"
        except pipeline.ErrorAnalisis as e:
            trabajo["error"] = str(e)
            trabajo["estado"] = "error"
        except Exception as e:  # noqa: BLE001
            _registrar_error("análisis")
            trabajo["error"] = (f"Ocurrió un error inesperado ({type(e).__name__}: {e}). "
                                "Se guardó el detalle en datos/errores.log.")
            trabajo["estado"] = "error"

    threading.Thread(target=ejecutar, daemon=True).start()
    return {"id": id_trabajo}


@app.get("/api/trabajos/{id_trabajo}")
def estado_trabajo(id_trabajo: str) -> dict:
    with _trabajos_lock:
        trabajo = _trabajos.get(id_trabajo)
    if not trabajo:
        raise HTTPException(status_code=404, detail="No se encontró ese análisis.")
    progreso: pipeline.Progreso = trabajo["progreso"]
    respuesta = {"estado": trabajo["estado"], "pasos": progreso.a_lista(), "porcentaje": progreso.porcentaje}
    if trabajo["estado"] == "listo":
        respuesta["resultado"] = trabajo["resultado"]
        respuesta["porcentaje"] = 100
    if trabajo["estado"] == "error":
        respuesta["error"] = trabajo["error"]
    return respuesta


@app.get("/api/historial")
def listar_historial() -> list[dict]:
    return historial.listar()


@app.get("/api/historial/{id_analisis}")
def ver_historial(id_analisis: int) -> dict:
    resultado = historial.obtener(id_analisis)
    if not resultado:
        raise HTTPException(status_code=404, detail="Ese análisis ya no está en el historial.")
    return resultado


@app.delete("/api/historial/{id_analisis}")
def borrar_historial(id_analisis: int) -> dict:
    return {"borrado": historial.borrar(id_analisis)}


@app.delete("/api/historial")
def borrar_todo_historial() -> dict:
    return {"borrados": historial.borrar_todo()}


@app.get("/api/estado")
def estado() -> dict:
    cfg = config.obtener()
    listas = dominios.listas()
    with _actualizacion_lock:
        actualizacion = dict(_actualizacion)
    return {
        "version": __version__,
        "indice": indice_claimreview.info(),
        "listas": listas.cantidades,
        "umbrales": config.valor(cfg, "etiquetas", {}),
        "base": config.valor(cfg, "puntaje.base", 50),
        "actualizacion": actualizacion,
    }


@app.post("/api/actualizar")
def iniciar_actualizacion(pedido: PedidoActualizacion) -> dict:
    with _actualizacion_lock:
        if _actualizacion["estado"] == "en_curso":
            raise HTTPException(status_code=429, detail="Ya se están actualizando los datos.")
        _actualizacion.update(estado="en_curso", mensaje="Comenzando…", resultado=None, inicio=time.time())

    def mensaje(texto: str) -> None:
        with _actualizacion_lock:
            _actualizacion["mensaje"] = texto

    def ejecutar() -> None:
        try:
            resultado = actualizar.actualizar_todo(mensaje, incluir_feed=pedido.incluir_feed)
            errores = list(resultado["listas"]["errores"])
            if "error" in (resultado.get("claimreview") or {}):
                errores.append(f"Base de verificaciones: {resultado['claimreview']['error']}")
            with _actualizacion_lock:
                _actualizacion.update(estado="error" if errores else "lista", resultado=resultado,
                                      mensaje="; ".join(errores) if errores else "Datos actualizados.")
        except Exception as e:  # noqa: BLE001
            _registrar_error("actualización")
            with _actualizacion_lock:
                _actualizacion.update(estado="error", mensaje=f"Error inesperado: {e}")

    threading.Thread(target=ejecutar, daemon=True).start()
    return {"estado": "en_curso"}


@app.get("/api/actualizacion")
def estado_actualizacion() -> dict:
    with _actualizacion_lock:
        return dict(_actualizacion)
