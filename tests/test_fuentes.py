import pytest

from verificanoticias import red
from verificanoticias.extraccion import desde_texto, desde_url
from verificanoticias.fuentes import duckduckgo, gdelt, google_news

from .conftest import leer, respuesta


def test_gdelt_interpreta_articulos(monkeypatch):
    llamadas = []

    def falso_obtener(url, params=None, **kw):
        llamadas.append(params)
        return respuesta(leer("gdelt.json"), url=url)

    monkeypatch.setattr(red, "obtener", falso_obtener)
    monkeypatch.setattr(gdelt, "_esperar_turno", lambda s: None)
    resultado = gdelt.buscar('"papa Francisco" murió', "es")
    assert resultado.estado == "ok"
    assert len(resultado.articulos) == 3
    primero = resultado.articulos[0]
    assert primero["dominio"] == "clarin.com"
    assert primero["fecha"].startswith("2025-04-21T08:00")
    assert "sourcelang:spanish" in llamadas[0]["query"]
    assert resultado.consultas and resultado.consultas[0].startswith("https://api.gdeltproject.org/")
    # La segunda vez sale de la caché, sin volver a consultar.
    otra = gdelt.buscar('"papa Francisco" murió', "es")
    assert otra.desde_cache and len(llamadas) == 1


def test_gdelt_limite_de_consultas(monkeypatch):
    texto = "Please limit requests to one every 5 seconds or contact us for larger queries."
    monkeypatch.setattr(red, "obtener", lambda url, params=None, **kw: respuesta(texto, url=url))
    monkeypatch.setattr(gdelt, "_esperar_turno", lambda s: None)
    resultado = gdelt.buscar("inflacion argentina", "es")
    assert resultado.estado == "error"
    assert resultado.tipo_error == red.LIMITE
    assert "5 segundos" in resultado.mensaje


def test_gdelt_armar_consulta_descarta_terminos_cortos():
    assert gdelt.armar_consulta(["Javier Milei", "FMI", "a", "dólar", "préstamo", "extra"]) == '"Javier Milei" FMI dólar préstamo'


def test_google_news_rss(monkeypatch):
    monkeypatch.setattr(red, "obtener", lambda url, params=None, **kw: respuesta(leer("google_news.xml"), url=url))
    resultado = google_news.buscar("papa Francisco murió", "es")
    assert resultado.estado == "ok"
    titulos = [a["titulo"] for a in resultado.articulos]
    assert "Falleció el papa Francisco en el Vaticano a los 88 años" in titulos
    nacion = resultado.articulos[0]
    assert nacion["dominio"] == "lanacion.com.ar" and nacion["medio"] == "La Nación"
    assert len(resultado.consultas) == 2  # dos ediciones en español


def test_fuente_que_no_responde(monkeypatch):
    def caido(url, **kw):
        raise red.ErrorRed(red.TIMEOUT, "news.google.com tardó demasiado en responder.")

    monkeypatch.setattr(red, "obtener", caido)
    resultado = google_news.buscar("algo", "es")
    assert resultado.estado == "error" and resultado.tipo_error == red.TIMEOUT
    assert not resultado.respondio


def test_duckduckgo_resultados_y_limite(monkeypatch):
    from ddgs.exceptions import RatelimitException

    class FalsoDDGS:
        def news(self, consulta, **kw):
            return [{"date": "2025-04-21T09:00:00+00:00", "title": "Murió el papa", "body": "El Vaticano confirmó",
                     "url": "https://www.infobae.com/x", "source": "Infobae"}]

        def text(self, consulta, **kw):
            raise RatelimitException("202 Ratelimit")

    monkeypatch.setattr(duckduckgo, "_ddgs", lambda: FalsoDDGS())
    noticias = duckduckgo.buscar_noticias("papa Francisco", "es")
    assert noticias.estado == "ok" and noticias.articulos[0]["dominio"] == "infobae.com"
    web = duckduckgo.buscar_web("papa Francisco falso", "es", nombre="DuckDuckGo (verificadores)")
    assert web.estado == "error" and web.tipo_error == red.LIMITE


def test_extraer_articulo_de_url(monkeypatch):
    monkeypatch.setattr(red, "obtener", lambda url, **kw: respuesta(leer("articulo.html"), url="https://www.diario.com/nota"))
    noticia = desde_url("https://www.diario.com/nota")
    assert noticia.titulo == "Murió el papa Francisco a los 88 años"
    assert noticia.autor == "María Gómez"
    assert noticia.fecha.startswith("2025-04-21")
    assert noticia.dominio == "diario.com"
    assert "Santa Marta" in noticia.cuerpo
    assert noticia.idioma == "es"


def test_sitio_que_bloquea_la_descarga(monkeypatch):
    def bloqueado(url, **kw):
        raise red.ErrorRed(red.BLOQUEADO, "www.diario.com bloqueó la descarga (error 403).")

    monkeypatch.setattr(red, "obtener", bloqueado)
    noticia = desde_url("www.diario.com/politica/murio-el-papa-francisco-a-los-88-anos-n123456")
    assert noticia.tipo_error == red.BLOQUEADO
    assert noticia.titulo == "murio el papa francisco a los 88 anos"
    assert noticia.url.startswith("https://")


def test_texto_pegado_separa_titular_y_cuerpo():
    noticia = desde_texto("Titular de la noticia\nPrimer párrafo del cuerpo.\nSegundo párrafo.")
    assert noticia.titulo == "Titular de la noticia"
    assert noticia.cuerpo.startswith("Primer párrafo")
    solo_titular = desde_texto("Murió el papa Francisco a los 88 años")
    assert solo_titular.titulo == "Murió el papa Francisco a los 88 años" and solo_titular.cuerpo == ""


@pytest.mark.parametrize("codigo, tipo", [(429, red.LIMITE), (403, red.BLOQUEADO), (404, red.NO_ENCONTRADO), (503, red.SERVIDOR)])
def test_errores_http_tienen_mensaje_claro(codigo, tipo):
    error = red._error_por_estado(respuesta(b"", url="https://sitio.com/x", estado=codigo))
    assert error.tipo == tipo
    assert "sitio.com" in error.mensaje
