import pytest

from verificanoticias.fuentes import claimreview as cr
from verificanoticias.fuentes import indice_claimreview

from .conftest import DATOS, leer


@pytest.mark.parametrize("veredicto, esperado", [
    ("Falso", cr.FALSO),
    ("False", cr.FALSO),
    ("Pants on Fire!", cr.FALSO),
    ("Not true", cr.FALSO),
    ("Parcialmente falso", cr.ENGANOSO),
    ("Mostly False", cr.ENGANOSO),
    ("Engañoso", cr.ENGANOSO),
    ("Sacado de contexto", cr.ENGANOSO),
    ("Insostenible", cr.SIN_EVIDENCIA),
    ("Verdadero, pero...", cr.MAYORMENTE_VERDADERO),
    ("Mostly True", cr.MAYORMENTE_VERDADERO),
    ("Verdadero", cr.VERDADERO),
    ("Labeled Satire", cr.SATIRA),
    ("Falso / No hay evidencia", cr.FALSO),
    ("Fact Crescendo Rating: False", cr.FALSO),
    ("xyz", cr.DESCONOCIDO),
])
def test_clasificar_veredicto(veredicto, esperado):
    assert cr.clasificar_veredicto(veredicto) == esperado


def test_clasificar_veredicto_numerico():
    assert cr.clasificar_veredicto("", 1, 5, 1) == cr.FALSO
    assert cr.clasificar_veredicto("", 3, 5, 1) == cr.ENGANOSO
    assert cr.clasificar_veredicto("", 5, 5, 1) == cr.VERDADERO


def test_veredicto_desde_titulo():
    assert cr.veredicto_desde_titulo("Es falso que el gobierno prohibió el asado") == cr.FALSO
    assert cr.veredicto_desde_titulo("Engañoso: la foto es de 2019") == cr.ENGANOSO
    assert cr.veredicto_desde_titulo("Qué se sabe del nuevo decreto") is None


def test_extraer_claimreview_de_html_con_graph_y_json_imperfecto():
    verificaciones = cr.extraer_de_html(leer("verificacion.html"), "https://verificador.example/pagina")
    assert len(verificaciones) == 2
    primera = cr.con_categoria(verificaciones[0])
    assert primera["afirmacion"] == "Las vacunas contra el COVID-19 causan infertilidad"
    assert primera["organizacion"] == "Verificador de Prueba"
    assert primera["categoria"] == cr.FALSO
    assert primera["fecha"].startswith("2021-06-30")
    assert primera["apariciones"] == ["https://www.facebook.com/post/1"]
    # El segundo bloque tiene comas sobrantes y no trae URL: se usa la de la página.
    assert verificaciones[1]["url"] == "https://verificador.example/pagina"
    assert cr.con_categoria(verificaciones[1])["categoria"] == cr.ENGANOSO


def test_extraer_de_html_vacio_o_roto():
    assert cr.extraer_de_html(b"") == []
    assert cr.extraer_de_html("<html><script type='application/ld+json'>{roto</script></html>") == []


def test_indice_local_construir_y_buscar(entorno):
    destino = entorno / "datos" / "claimreview.db"
    destino.parent.mkdir(parents=True, exist_ok=True)
    estadisticas = indice_claimreview.construir(DATOS / "feed_mini.json", destino)
    assert estadisticas["cantidad"] == 3
    assert estadisticas["publicadores"][0][0] == "fastcheck.cl"
    info = indice_claimreview.info()
    assert info["disponible"] and info["cantidad"] == 3
    encontradas = indice_claimreview.buscar(["vacunas", "infertilidad"])
    assert encontradas[0]["afirmacion"] == "Vacunas contra el Covid-19 causan infertilidad"
    assert encontradas[0]["organizacion"] == "Fast Check CL"
    assert indice_claimreview.buscar(["palabrainexistente"]) == []
