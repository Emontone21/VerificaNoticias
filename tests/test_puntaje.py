from datetime import datetime, timedelta, timezone

from verificanoticias import puntaje, senales
from verificanoticias.extraccion import Noticia, desde_texto

AHORA = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def _fecha(dias_atras: float) -> str:
    return (AHORA - timedelta(days=dias_atras)).isoformat()


def _articulo(dominio, categoria="confiable", grupo=None, dias=1):
    return {"titulo": f"Nota de {dominio}", "url": f"https://{dominio}/nota", "dominio": dominio, "medio": dominio,
            "categoria": categoria, "grupo": grupo or dominio, "similitud": 0.5, "fecha": _fecha(dias)}


def _evidencia(**cambios):
    base = {
        "ahora": AHORA.isoformat(),
        "noticia": {"tipo": "texto", "tiene_texto": False},
        "verificaciones": {"fuertes": [], "sin_marcado": []},
        "cobertura": {"consultada": True, "fuentes_consultadas": ["GDELT", "Google News"], "fuentes_fallidas": [],
                      "coincidencias": []},
        "fuente": {},
        "alertas": {},
        "fecha_noticia": None,
        "noticia_vieja": {"detectada": False},
    }
    base.update(cambios)
    return base


def _suma_cuadra(resultado):
    """El puntaje final debe ser exactamente la base más todas las filas del desglose."""
    return resultado["base"] + sum(s["puntos"] for s in resultado["senales"]) == resultado["puntaje"]


def test_confirmada_con_tres_medios_confiables_independientes():
    coincidencias = [_articulo("clarin.com", grupo="clarin"), _articulo("tn.com.ar", grupo="clarin"),
                     _articulo("elpais.com"), _articulo("reuters.com"), _articulo("blog.net", categoria=None)]
    r = puntaje.calcular(_evidencia(
        noticia={"tipo": "url", "tiene_texto": True},
        fuente={"categoria": "confiable", "dominio": "lanacion.com.ar", "antiguedad": {"dias": 9000}},
        cobertura={"consultada": True, "coincidencias": coincidencias, "fuentes_consultadas": ["GDELT"]},
    ))
    assert r["medios_confiables_independientes"] == 3  # Clarín y TN cuentan como un solo grupo
    assert r["clave_etiqueta"] == "confirmada"
    assert r["puntaje"] >= 80
    assert _suma_cuadra(r)


def test_desmentida_por_verificador_tiene_prioridad():
    falso = {"categoria": "falso", "veredicto": "Falso", "organizacion": "Chequeado", "url": "https://chequeado.com/x",
             "afirmacion": "X", "fecha": _fecha(10)}
    r = puntaje.calcular(_evidencia(
        verificaciones={"fuertes": [falso], "sin_marcado": []},
        cobertura={"consultada": True, "coincidencias": [_articulo("blog.net", categoria=None)], "fuentes_consultadas": ["GDELT"]},
    ))
    assert r["clave_etiqueta"] == "desmentida"
    assert r["etiqueta"] == "Desmentida por verificadores"
    assert r["puntaje"] <= 10
    assert _suma_cuadra(r)


def test_verificacion_vieja_y_cobertura_posterior_es_dudosa():
    """Un rumor desmentido hace años que ahora sí ocurrió no debe quedar como "desmentido"."""
    falso = {"categoria": "falso", "veredicto": "Pants on Fire", "organizacion": "PolitiFact",
             "url": "https://politifact.com/x", "afirmacion": "Pope Francis is dead.", "fecha": _fecha(900)}
    coincidencias = [_articulo("reuters.com", dias=2), _articulo("apnews.com", dias=2), _articulo("bbc.com", dias=1)]
    r = puntaje.calcular(_evidencia(
        verificaciones={"fuertes": [falso], "sin_marcado": []},
        cobertura={"consultada": True, "coincidencias": coincidencias, "fuentes_consultadas": ["GDELT"]},
    ))
    assert r["clave_etiqueta"] == "dudosa"
    assert any(s["clave"] == "verificacion_antigua" for s in r["senales"])


def test_veredicto_verdadero_eleva_el_puntaje():
    verdadero = {"categoria": "verdadero", "veredicto": "Verdadero", "organizacion": "Newtral", "url": "https://newtral.es/x",
                 "afirmacion": "X", "fecha": _fecha(5)}
    r = puntaje.calcular(_evidencia(verificaciones={"fuertes": [verdadero], "sin_marcado": []}))
    assert r["clave_etiqueta"] == "confirmada" and r["puntaje"] >= 85


def test_sin_datos_si_fallaron_las_busquedas():
    r = puntaje.calcular(_evidencia(
        cobertura={"consultada": False, "coincidencias": [], "fuentes_fallidas": ["GDELT", "Google News", "DuckDuckGo"]},
    ))
    assert r["clave_etiqueta"] == "sin_datos"
    assert "NO significa que sea falsa" in r["explicacion"]


def test_alto_impacto_sin_cobertura_depende_de_la_antiguedad():
    alertas = {"alto_impacto": ["murio"]}
    vieja = puntaje.calcular(_evidencia(alertas=alertas, fecha_noticia=_fecha(5)))
    reciente = puntaje.calcular(_evidencia(alertas=alertas, fecha_noticia=_fecha(0.5)))
    desconocida = puntaje.calcular(_evidencia(alertas=alertas))
    puntos = lambda r: next(s["puntos"] for s in r["senales"] if s["clave"] == "sin_cobertura_alto_impacto")
    assert puntos(vieja) == -20 and puntos(reciente) == -5 and puntos(desconocida) == -12
    assert any("reciente" in a for a in reciente["avisos"])
    assert vieja["clave_etiqueta"] == "probablemente_falsa"
    # No es "desmentida": solo falta confirmación.
    assert vieja["clave_etiqueta"] != "desmentida"


def test_sitio_desinformacion_imitacion_y_dominio_nuevo():
    r = puntaje.calcular(_evidencia(
        noticia={"tipo": "url", "tiene_texto": True},
        fuente={"categoria": None, "dominio": "c1arin.com", "antiguedad": {"dias": 30, "fecha_creacion": _fecha(30)},
                "imitacion": {"imita": "clarin.com", "motivo": "«c1arin» se ve casi igual que «clarin»"}},
        alertas={"alto_impacto": ["murio"], "palabras_gancho": ["urgente", "compartelo"],
                 "mayusculas": {"detectada": True, "ejemplos": ["URGENTE"]},
                 "exclamaciones": {"detectada": True, "en_titulo": 4, "en_texto": 0}},
        fecha_noticia=_fecha(5),
    ))
    claves = {s["clave"] for s in r["senales"]}
    assert {"imitacion", "dominio_nuevo", "palabras_gancho", "mayusculas", "exclamaciones"} <= claves
    assert r["puntaje"] == 0
    assert r["clave_etiqueta"] == "probablemente_falsa"
    assert any(s["clave"] == "limite" for s in r["senales"])
    assert _suma_cuadra(r)


def test_tope_de_alertas():
    alertas = {"palabras_gancho": ["a", "b", "c", "d", "e"], "mayusculas": {"detectada": True},
               "exclamaciones": {"detectada": True}, "titular_cuerpo": {"detectada": True, "proporcion": 0.1},
               "fuentes_citadas": {"evaluado": True, "cantidad": 0},
               "autor": {"evaluado": True, "valor": ""}, "fecha": {"evaluado": True, "valor": None}}
    r = puntaje.calcular(_evidencia(alertas=alertas, noticia_vieja={"detectada": True, "motivo": "vieja"}))
    total_alertas = sum(s["puntos"] for s in r["senales"] if s["grupo"] == "alertas")
    assert total_alertas == -35


def test_detectar_senales_de_alerta():
    noticia = desde_texto("¡¡URGENTE!! MURIÓ EL FAMOSO ACTOR\n" + "Compártelo antes de que lo borren. " * 3 +
                          "Esto es increíble y nadie habla de esto. " * 8)
    detectadas = senales.detectar(noticia)
    assert detectadas["mayusculas"]["detectada"]
    assert detectadas["exclamaciones"]["detectada"]
    assert {"urgente", "compartelo", "antes de que lo borren", "increible", "nadie habla de esto"} <= set(detectadas["palabras_gancho"])
    assert detectadas["alto_impacto"]
    assert detectadas["fuentes_citadas"]["cantidad"] == 0


def test_senales_de_calidad_en_nota_con_fuentes():
    cuerpo = ("Según informó el Ministerio de Salud en un comunicado, la campaña comenzará el lunes. "
              "\"Tenemos dosis suficientes para toda la población\", dijo la ministra en conferencia de prensa. ") * 3
    noticia = Noticia(tipo="url", titulo="Comienza la campaña de vacunación", cuerpo=cuerpo, autor="Ana Pérez",
                      fecha="2026-10-01T00:00:00+00:00", idioma="es")
    detectadas = senales.detectar(noticia)
    assert detectadas["fuentes_citadas"]["cantidad"] >= 2
    r = puntaje.calcular(_evidencia(noticia={"tipo": "url", "tiene_texto": True}, alertas=detectadas,
                                    fuente={"categoria": "confiable", "dominio": "x.com", "antiguedad": {}}))
    claves = {s["clave"] for s in r["senales"]}
    assert {"cita_fuentes", "autor_y_fecha"} <= claves
