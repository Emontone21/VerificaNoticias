import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from verificanoticias import config, dominios, historial, pipeline, red
from verificanoticias.fuentes import duckduckgo, gdelt, google_news, verificadores, wikipedia
from verificanoticias.fuentes.base import ResultadoFuente



def _articulo(titulo, url, dominio, fecha, fuente="GDELT"):
    return {"titulo": titulo, "url": url, "dominio": dominio, "fecha": fecha, "resumen": "", "medio": dominio,
            "fuente_busqueda": fuente, "idioma": "es"}


@pytest.fixture
def fuentes_simuladas(monkeypatch):
    """Simula todas las fuentes externas con una noticia real y bien cubierta."""
    hace = lambda horas: (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    cobertura = [
        _articulo("Murió el papa Francisco a los 88 años", "https://www.clarin.com/a", "clarin.com", hace(5)),
        _articulo("Muere el papa Francisco a los 88 años en el Vaticano", "https://elpais.com/b", "elpais.com", hace(4)),
        _articulo("Falleció el papa Francisco a los 88 años", "https://www.reuters.com/c", "reuters.com", hace(6)),
        _articulo("Murió el papa Francisco: el Vaticano confirmó su muerte a los 88 años", "https://www.infobae.com/d", "infobae.com", hace(3)),
        _articulo("Es falso que murió el papa Francisco a los 88 años", "https://www.lanacion.com.ar/e", "lanacion.com.ar", hace(900 * 24)),
    ]
    monkeypatch.setattr(gdelt, "buscar", lambda consulta, idioma, **kw: ResultadoFuente(nombre="GDELT", articulos=cobertura[:3]))
    monkeypatch.setattr(gdelt, "buscar_en_dominios", lambda *a, **kw: ResultadoFuente(nombre="GDELT (verificadores)", estado="sin_resultados"))
    monkeypatch.setattr(google_news, "buscar", lambda consulta, idioma: ResultadoFuente(nombre="Google News", articulos=cobertura[3:]))
    monkeypatch.setattr(duckduckgo, "buscar_noticias", lambda consulta, idioma: ResultadoFuente(
        nombre="DuckDuckGo", estado="error", tipo_error=red.LIMITE, mensaje="DuckDuckGo limitó las búsquedas."))
    monkeypatch.setattr(verificadores, "buscar_en_duckduckgo", lambda consulta, idioma: ResultadoFuente(
        nombre="DuckDuckGo (verificadores)", estado="sin_resultados"))
    monkeypatch.setattr(verificadores, "leer_paginas", lambda candidatos, referencia: ResultadoFuente(
        nombre="Páginas de verificadores", estado="sin_resultados", extra={"verificaciones": [], "sin_marcado": []}))
    monkeypatch.setattr(dominios, "antiguedad", lambda d: {"dominio": d, "fecha_creacion": "1998-01-01T00:00:00+00:00",
                                                           "dias": 10000, "metodo": "RDAP", "consulta": "https://rdap.org/domain/x", "error": None})
    monkeypatch.setattr(wikipedia, "resumenes", lambda entidades, idioma: ([{
        "titulo": "Francisco (papa)", "descripcion": "papa de la Iglesia católica", "extracto": "Jorge Mario Bergoglio...",
        "url": "https://es.wikipedia.org/wiki/Francisco_(papa)", "idioma": "es", "entidad": "Francisco", "tipo": "persona"}], []))
    monkeypatch.setattr(pipeline, "_texto_articulo", lambda url: (
        "El papa Francisco murió este lunes a los 88 años en su residencia de Santa Marta, según informó el Vaticano. "
        "Miles de fieles se reunieron en la plaza San Pedro para rezar por el pontífice argentino fallecido hoy."))


def test_pipeline_noticia_confirmada(fuentes_simuladas):
    resultado = pipeline.analizar("Murió el papa Francisco a los 88 años en el Vaticano")
    res = resultado["resultado"]
    assert res["clave_etiqueta"] == "confirmada", res
    assert res["medios_confiables_independientes"] >= 3
    # La nota de La Nación que desmiente no cuenta como cobertura a favor.
    assert all("falso" not in a["titulo"].lower() for a in resultado["cobertura"]["coincidencias"])
    assert resultado["cobertura"]["desmentidas_en_medios"]
    contexto = resultado["contexto"]
    assert contexto["linea_de_tiempo"][0]["dominio"] == "reuters.com"  # la más antigua primero
    assert contexto["resumen"] and contexto["resumen"][0]["url"].startswith("https://")
    assert contexto["wikipedia"][0]["titulo"] == "Francisco (papa)"
    nombres = {f["nombre"]: f["estado"] for f in resultado["fuentes_consultadas"]}
    assert nombres["DuckDuckGo"] == "error" and nombres["GDELT"] == "ok"
    assert any("DuckDuckGo" in a for a in resultado["advertencias"])
    # Se guardó en el historial.
    assert historial.obtener(resultado["id"])["resultado"]["puntaje"] == res["puntaje"]


def test_pipeline_sin_internet(monkeypatch):
    monkeypatch.setattr(red, "hay_internet", lambda forzar=False: False)
    resultado = pipeline.analizar("¡¡URGENTE!! Murió el famoso actor. Compártelo antes de que lo borren")
    assert resultado["resultado"]["clave_etiqueta"] == "sin_datos"
    assert any("internet" in a for a in resultado["advertencias"])
    estados = {f["nombre"]: f.get("tipo_error") for f in resultado["fuentes_consultadas"]}
    assert estados["GDELT"] == red.SIN_INTERNET


def test_validar_entrada():
    with pytest.raises(pipeline.ErrorAnalisis):
        pipeline.validar_entrada("   ")
    with pytest.raises(pipeline.ErrorAnalisis):
        pipeline.validar_entrada("hola che")
    assert pipeline.validar_entrada("www.sitio.com/nota") == "www.sitio.com/nota"


# ----------------------------------------------------------------------
# Servidor web
# ----------------------------------------------------------------------

@pytest.fixture
def cliente():
    from verificanoticias.web.app import app

    return TestClient(app)


def test_pagina_principal_y_estado(cliente):
    r = cliente.get("/")
    assert r.status_code == 200 and "ayuda para decidir, no una verdad absoluta" in r.text
    estado = cliente.get("/api/estado").json()
    assert estado["indice"]["disponible"] is False
    assert estado["umbrales"]["confirmada"] == 80


def test_rechaza_pedidos_de_otros_sitios(cliente):
    r = cliente.get("/api/estado", headers={"Host": "sitio-malicioso.com"})
    assert r.status_code == 400


def test_analisis_por_api_e_historial(cliente, monkeypatch):
    def analizar_falso(texto, progreso):
        progreso.iniciar("entrada")
        progreso.terminar("entrada")
        resultado = {"fecha_analisis": "2026-10-13T12:00:00+00:00", "entrada": texto,
                     "noticia": {"titulo": texto}, "resultado": {"puntaje": 42, "etiqueta": "Dudosa", "clave_etiqueta": "dudosa"}}
        resultado["id"] = historial.guardar(resultado)
        return resultado

    monkeypatch.setattr(pipeline, "analizar", analizar_falso)
    assert cliente.post("/api/analizar", json={"texto": "hola"}).status_code == 400
    id_trabajo = cliente.post("/api/analizar", json={"texto": "Una noticia de prueba con varias palabras"}).json()["id"]
    for _ in range(50):
        datos = cliente.get(f"/api/trabajos/{id_trabajo}").json()
        if datos["estado"] != "en_curso":
            break
        time.sleep(0.05)
    assert datos["estado"] == "listo" and datos["resultado"]["resultado"]["puntaje"] == 42
    lista = cliente.get("/api/historial").json()
    assert len(lista) == 1 and lista[0]["etiqueta"] == "Dudosa"
    assert cliente.get(f"/api/historial/{lista[0]['id']}").json()["resultado"]["puntaje"] == 42
    assert cliente.delete(f"/api/historial/{lista[0]['id']}").json()["borrado"] is True
    assert cliente.get("/api/historial").json() == []


def test_config_usuario_pisa_valores_y_avisa_errores(entorno):
    (entorno / "config.yaml").write_text("puntaje:\n  base: 60\n", encoding="utf-8")
    config.establecer(None)
    cfg = config.obtener()
    assert cfg["puntaje"]["base"] == 60
    assert cfg["puntaje"]["fuente"]["satira"] == -20  # lo demás queda con el valor original
    (entorno / "config.yaml").write_text("puntaje:\n  base: 60\n   fuente: [\n", encoding="utf-8")
    with pytest.raises(config.ErrorConfig, match="línea"):
        config.cargar()
