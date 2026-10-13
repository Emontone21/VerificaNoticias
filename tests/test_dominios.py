import pytest

from verificanoticias import dominios


@pytest.fixture
def listas(tmp_path):
    manual = tmp_path / "manual"
    importadas = tmp_path / "importadas"
    manual.mkdir()
    importadas.mkdir()
    (manual / "medios_confiables.csv").write_text(
        "dominio,nombre,pais,idioma,grupo,nota\n"
        "clarin.com,Clarín,Argentina,es,grupo clarin,\n"
        "tn.com.ar,TN,Argentina,es,grupo clarin,\n"
        "reuters.com,Reuters,Internacional,en,reuters,\n"
        "lanacion.com.ar,La Nación,Argentina,es,la nacion,\n"
        "elmundo.es,El Mundo,España,es,unidad editorial,\n",
        encoding="utf-8",
    )
    (manual / "verificadores.csv").write_text(
        "dominio,nombre,pais,idioma,nota\nreuters.com/fact-check,Reuters Fact Check,Internacional,en,\nchequeado.com,Chequeado,Argentina,es,\n",
        encoding="utf-8",
    )
    # Guardado desde Excel en español: separador ";" y codificación de Windows.
    (manual / "desinformacion.csv").write_bytes(
        "dominio;nombre;pais;motivo;fuente\nsitiofalso.com;Sitio Falso;Argentina;Inventa noticias;Prueba\n".encode("cp1252")
    )
    (manual / "satira.csv").write_text("dominio,nombre,pais,nota\nelmundotoday.com,El Mundo Today,España,Humor\n", encoding="utf-8")
    (importadas / "domain_quality.csv").write_text(
        "dominio,puntaje,categoria\nsitiofalso.com,0.9,confiable\ninfowars.com,0.05,desinformacion\n", encoding="utf-8"
    )
    return dominios.Listas.cargar(manual, importadas)


def test_clasificar_por_dominio_y_subdominio(listas):
    c = listas.clasificar("https://www.clarin.com/politica/nota.html")
    assert c.categoria == dominios.CONFIABLE and c.grupo == "grupo clarin"
    assert listas.clasificar("https://edicion.tn.com.ar/x").grupo == "grupo clarin"


def test_clasificar_por_seccion(listas):
    assert listas.clasificar("https://www.reuters.com/fact-check/abc").categoria == dominios.VERIFICADOR
    assert listas.clasificar("https://www.reuters.com/world/abc").categoria == dominios.CONFIABLE


def test_lista_manual_tiene_prioridad_sobre_importada(listas):
    c = listas.clasificar("sitiofalso.com")
    assert c.categoria == dominios.DESINFORMACION
    assert "tu lista" in c.origen
    assert listas.clasificar("infowars.com").categoria == dominios.DESINFORMACION
    assert listas.clasificar("blogcualquiera.net").categoria is None


@pytest.mark.parametrize("host, imita", [
    ("c1arin.com", "clarin.com"),
    ("clarin-noticias.com", "clarin.com"),
    ("clarin.com.noticias-hoy.xyz", "clarin.com"),
    ("clarin.com.co", "clarin.com"),
    ("reutres.com", "reuters.com"),
    ("lanacoin.com.ar", "lanacion.com.ar"),
    ("chequeado-oficial.com", "chequeado.com"),
])
def test_detectar_imitaciones(listas, host, imita):
    resultado = dominios.detectar_imitacion(host, listas)
    assert resultado is not None and resultado["imita"] == imita


def test_detectar_imitacion_con_letras_de_otro_alfabeto(listas):
    puny = "clarín".encode("idna").decode() + ".com"
    assert dominios.detectar_imitacion(puny, listas)["imita"] == "clarin.com"
    assert dominios.detectar_imitacion("clаrin.com", listas)["imita"] == "clarin.com"  # "а" cirílica


@pytest.mark.parametrize("host", ["clarin.com", "noticiasdelmundo.com", "elmundo.com", "elmundotoday.com", "blog.net"])
def test_no_marca_dominios_legitimos_o_genericos(listas, host):
    assert dominios.detectar_imitacion(host, listas) is None


def test_antiguedad_por_rdap(monkeypatch):
    from verificanoticias import red

    from .conftest import respuesta

    rdap = '{"events": [{"eventAction": "registration", "eventDate": "2020-01-15T00:00:00Z"}]}'
    monkeypatch.setattr(red, "obtener", lambda url, **kw: respuesta(rdap, url="https://rdap.example/domain/x.com"))
    resultado = dominios.antiguedad("https://www.noticias.x.com/nota")
    assert resultado["dominio"] == "x.com"
    assert resultado["metodo"] == "RDAP"
    assert resultado["fecha_creacion"].startswith("2020-01-15")
    assert resultado["dias"] > 365
