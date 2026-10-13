from verificanoticias import similitud, texto


def test_normalizar_quita_tildes_y_signos():
    assert texto.normalizar("¡¡URGENTE!! Murió el Dr. Pérez") == "urgente murio el dr perez"


def test_detectar_idioma():
    assert texto.detectar_idioma("El gobierno anunció que la inflación bajó en septiembre") == "es"
    assert texto.detectar_idioma("The president said that the economy is growing") == "en"


def test_dividir_frases_respeta_abreviaturas():
    frases = texto.dividir_frases("El Dr. Pérez llegó el lunes. Dijo que todo está bien. ¿Será verdad?")
    assert frases == ["El Dr. Pérez llegó el lunes.", "Dijo que todo está bien.", "¿Será verdad?"]


def test_buscar_expresiones_con_prefijos_y_frases():
    encontradas = texto.buscar_expresiones(
        "URGENTE: falleció el actor. Compártelo antes de que lo borren",
        ["urgente", "falleci*", "compártelo", "antes de que lo borren"],
    )
    assert encontradas == ["urgente", "fallecio", "compartelo", "antes de que lo borren"]


def test_quitar_expresiones_respeta_el_texto_original():
    limpio = texto.quitar_expresiones("¡URGENTE! Murió el papa Francisco. Compártelo ya", ["urgente", "compartelo"])
    assert "Murió el papa Francisco" in limpio
    assert "URGENTE" not in limpio and "Compártelo" not in limpio


def test_similitud_distingue_misma_noticia_de_otra():
    referencia = "Murió el papa Francisco a los 88 años en el Vaticano"
    misma, otra, ajena = similitud.similitudes(referencia, [
        "Falleció el papa Francisco, el primer pontífice latinoamericano, a los 88 años",
        "El papa Francisco celebró la misa de Pascua en la plaza San Pedro",
        "Messi marcó dos goles en la victoria de Inter Miami",
    ])
    assert misma > 0.3
    assert misma > otra > ajena
    assert ajena < 0.05


def test_cobertura_ponderada_detecta_palabra_distintiva():
    referencia = "Las vacunas contra el COVID-19 causan infertilidad en mujeres jóvenes"
    igual, distinta = similitud.cobertura_ponderada(referencia, [
        "Vacunas contra el Covid-19 causan infertilidad",
        "Las vacunas contra el covid-19 causan VIH",
    ])
    assert igual == 1.0
    assert distinta < 0.8


def test_cobertura_de_palabras_titular_cuerpo():
    assert similitud.cobertura_de_palabras("Murió el papa Francisco", "El papa Francisco murió este lunes") == 1.0
    assert similitud.cobertura_de_palabras("Descubren cura milagrosa contra cáncer",
                                           "El clima del fin de semana será soleado en la capital") == 0.0
