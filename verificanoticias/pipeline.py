"""Orquesta el análisis completo de una noticia."""

from __future__ import annotations

import concurrent.futures
import re
import threading
import time
from datetime import datetime, timezone

from . import cache, config, dominios, historial, nlp, puntaje, red, resumen, senales, similitud, texto
from .extraccion import Noticia, _titulo_desde_url, es_url, leer, normalizar_url
from .fuentes import claimreview, duckduckgo, gdelt, google_news, indice_claimreview, verificadores, wikipedia
from .fuentes.base import ResultadoFuente, a_datetime, dominio_de

PASOS = [
    ("entrada", "Leyendo la noticia"),
    ("palabras", "Detectando palabras clave y nombres propios"),
    ("busquedas", "Buscando verificaciones y cobertura en otros medios"),
    ("verificadores", "Leyendo las páginas de los verificadores"),
    ("fuente", "Analizando la fuente y las señales de alerta"),
    ("puntaje", "Calculando el puntaje"),
    ("contexto", "Armando línea de tiempo, resumen y contexto"),
]
ETIQUETAS_CONFIABLES = ("confirmada", "probablemente_verdadera")
MAX_CARACTERES_ENTRADA = 50000


class ErrorAnalisis(Exception):
    """Error que se muestra tal cual al usuario."""


class Progreso:
    def __init__(self, al_cambiar=None) -> None:
        self.pasos = [{"id": i, "nombre": n, "estado": "pendiente", "detalle": ""} for i, n in PASOS]
        self._al_cambiar = al_cambiar
        self._lock = threading.Lock()

    def _actualizar(self, paso: str, estado: str, detalle: str = "") -> None:
        with self._lock:
            for p in self.pasos:
                if p["id"] == paso:
                    p["estado"] = estado
                    p["detalle"] = detalle
        if self._al_cambiar:
            self._al_cambiar(self)

    def iniciar(self, paso: str, detalle: str = "") -> None:
        self._actualizar(paso, "en_curso", detalle)

    def terminar(self, paso: str, detalle: str = "") -> None:
        self._actualizar(paso, "listo", detalle)

    def omitir(self, paso: str, detalle: str = "") -> None:
        self._actualizar(paso, "omitido", detalle)

    @property
    def porcentaje(self) -> int:
        with self._lock:
            hechos = sum(1 for p in self.pasos if p["estado"] in ("listo", "omitido"))
            en_curso = sum(1 for p in self.pasos if p["estado"] == "en_curso")
        return int((hechos + en_curso * 0.4) / len(self.pasos) * 100)

    def a_lista(self) -> list[dict]:
        with self._lock:
            return [dict(p) for p in self.pasos]


def validar_entrada(entrada: str) -> str:
    entrada = (entrada or "").strip()
    if not entrada:
        raise ErrorAnalisis("Pega el texto, el titular o el link de la noticia.")
    if len(entrada) > MAX_CARACTERES_ENTRADA:
        entrada = entrada[:MAX_CARACTERES_ENTRADA]
    if not es_url(entrada) and len(texto.palabras(entrada)) < 4:
        raise ErrorAnalisis("Escribe al menos un titular completo (4 palabras o más) para poder buscarlo.")
    return entrada


# ----------------------------------------------------------------------
# Pasos auxiliares
# ----------------------------------------------------------------------

def _buscar_en_indice(terminos: list[str]) -> ResultadoFuente:
    resultado = ResultadoFuente(nombre=indice_claimreview.NOMBRE_FUENTE)
    estado = indice_claimreview.info()
    if not estado["disponible"]:
        resultado.estado = "omitida"
        resultado.mensaje = ("La base local de verificaciones no está descargada. Usa el botón «Actualizar datos» "
                             "(descarga unos 200 MB una sola vez).")
        return resultado
    inicio = time.time()
    try:
        encontradas = indice_claimreview.buscar(terminos)
    except Exception as e:  # noqa: BLE001
        resultado.estado = "error"
        resultado.mensaje = f"No se pudo consultar la base local: {e}"
        return resultado
    resultado.extra = {"verificaciones": encontradas, "con_datos": True}
    resultado.estado = "ok" if encontradas else "sin_resultados"
    cantidad = f"{estado['cantidad']:,}".replace(",", ".")
    fecha = a_datetime(estado.get("fecha_actualizacion"))
    resultado.mensaje = (f"{len(encontradas)} verificaciones con palabras en común "
                         f"(base de {cantidad} verificaciones{f' del {fecha:%d/%m/%Y}' if fecha else ''})")
    if estado.get("desactualizado"):
        resultado.mensaje += ". La base tiene más de una semana: conviene actualizarla."
    resultado.duracion = round(time.time() - inicio, 2)
    return resultado


def _clasificar_articulos(articulos: list[dict], listas: dominios.Listas, referencia: str) -> list[dict]:
    """Quita duplicados, clasifica el dominio y mide la similitud con la noticia."""
    unicos: list[dict] = []
    vistos_url: set[str] = set()
    vistos_titulo: set[tuple[str, str]] = set()
    for a in articulos:
        clave_titulo = (a.get("dominio", ""), texto.normalizar(a.get("titulo", ""))[:80])
        if not a.get("url") or a["url"] in vistos_url or (clave_titulo[1] and clave_titulo in vistos_titulo):
            continue
        vistos_url.add(a["url"])
        vistos_titulo.add(clave_titulo)
        unicos.append(dict(a))
    if not unicos:
        return []
    puntajes = similitud.similitudes(referencia, [f"{a.get('titulo', '')}. {a.get('resumen', '')}" for a in unicos])
    for a, s in zip(unicos, puntajes):
        objetivo = a["url"] if dominio_de(a["url"]) == a.get("dominio") or not a.get("dominio") else a["dominio"]
        c = listas.clasificar(objetivo)
        a["dominio"] = a.get("dominio") or c.host
        a["similitud"] = s
        a["categoria"] = c.categoria
        a["nombre_categoria"] = c.nombre_categoria
        a["grupo"] = c.grupo
        a["es_verificador"] = c.es_verificador or c.categoria == dominios.VERIFICADOR
        a["desmiente"] = _titulo_desmiente(a.get("titulo", ""))
        if not a.get("medio"):
            a["medio"] = c.nombre or a["dominio"]
    unicos.sort(key=lambda a: a["similitud"], reverse=True)
    return unicos


_RE_DESMENTIDA = re.compile(
    r"\b(desmient\w*|desminti\w*|debunk\w*|fact.?check\w*|bulo|hoax|enga[nñ]oso|es falso|son falsos?|"
    r"no es cierto|no es verdad|falsa noticia|noticia falsa|fake news|false claim|verificaci[oó]n)\b",
    re.IGNORECASE,
)


def _titulo_desmiente(titulo: str) -> bool:
    """El titular de un artículo indica que desmiente algo (no que lo informa)."""
    return bool(titulo) and (
        claimreview.veredicto_desde_titulo(titulo) in (claimreview.FALSO, claimreview.ENGANOSO)
        or bool(_RE_DESMENTIDA.search(titulo))
    )


def _noticia_vieja(noticia: Noticia, coincidencias: list[dict], cfg: dict, ahora: datetime) -> dict:
    a = config.valor(cfg, "alertas", {}) or {}
    dias_max = int(a.get("dias_noticia_vieja", 180))
    dias_recientes = int(a.get("dias_sin_cobertura_reciente", 30))
    fecha = a_datetime(noticia.fecha)
    if fecha and (ahora - fecha).days > dias_max:
        return {
            "detectada": True,
            "fecha": noticia.fecha,
            "motivo": f"La nota se publicó el {fecha:%d/%m/%Y} (hace {(ahora - fecha).days} días). "
                      "Si te la compartieron como algo actual, es una noticia vieja.",
        }
    fechadas = [(a_datetime(c.get("fecha")), c) for c in coincidencias if a_datetime(c.get("fecha"))]
    if noticia.tipo == "texto" and fechadas:
        mas_antigua = min(fechadas, key=lambda x: x[0])
        mas_reciente = max(fechadas, key=lambda x: x[0])
        if (ahora - mas_antigua[0]).days > dias_max and (ahora - mas_reciente[0]).days > dias_recientes:
            return {
                "detectada": True,
                "fecha": mas_antigua[1].get("fecha"),
                "motivo": f"Los artículos que dicen lo mismo son de entre el {mas_antigua[0]:%d/%m/%Y} y el "
                          f"{mas_reciente[0]:%d/%m/%Y}; no hay cobertura de los últimos {dias_recientes} días. "
                          "Puede ser una noticia vieja que vuelve a circular.",
                "evidencias": [{"titulo": mas_antigua[1].get("titulo"), "url": mas_antigua[1].get("url"),
                                "medio": mas_antigua[1].get("medio"), "fecha": mas_antigua[1].get("fecha")}],
            }
    return {"detectada": False}


def _texto_articulo(url: str) -> str:
    def descargar() -> str:
        import trafilatura

        respuesta = red.obtener(url, tipo="navegador")
        return trafilatura.extract(respuesta.content, url=respuesta.url) or ""

    contenido, _ = cache.con_cache("texto_articulo", url, cache.horas("articulos"), descargar)
    return contenido or ""


def _contexto(noticia: Noticia, coincidencias: list[dict], consultas: dict, referencia: str) -> dict:
    """Línea de tiempo, resumen extractivo y Wikipedia (solo para noticias confiables)."""
    errores: list[str] = []
    utiles = [a for a in coincidencias if a.get("categoria") not in ("desinformacion", "satira")]
    linea = resumen.linea_de_tiempo(utiles)

    # Hasta 5 artículos de grupos distintos, priorizando medios confiables y enlaces directos.
    candidatos = sorted(
        [a for a in utiles if "news.google.com" not in a["url"]],
        key=lambda a: (a.get("categoria") != "confiable", -a.get("similitud", 0)),
    )
    elegidos, grupos = [], set()
    for a in candidatos:
        if a.get("grupo") in grupos:
            continue
        grupos.add(a.get("grupo"))
        elegidos.append(a)
        if len(elegidos) >= 5:
            break
    documentos = []
    if noticia.tiene_texto:
        documentos.append({"texto": noticia.cuerpo, "url": noticia.url, "medio": noticia.sitio or noticia.dominio or "Texto analizado"})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ejecutor:
        futuros = {ejecutor.submit(_texto_articulo, a["url"]): a for a in elegidos}
        for futuro in concurrent.futures.as_completed(futuros):
            a = futuros[futuro]
            try:
                contenido = futuro.result()
            except red.ErrorRed as e:
                errores.append(f"{a.get('dominio')}: {e.mensaje}")
                continue
            if contenido:
                documentos.append({"texto": contenido, "url": a["url"], "medio": a.get("medio") or a.get("dominio")})
    frases = resumen.resumen_extractivo(documentos, referencia, noticia.idioma) if documentos else []
    wiki, errores_wiki = wikipedia.resumenes(consultas.get("entidades") or [], noticia.idioma)
    return {
        "linea_de_tiempo": linea,
        "resumen": frases,
        "articulos_resumidos": [{"url": d["url"], "medio": d["medio"]} for d in documentos if d.get("url")],
        "wikipedia": wiki,
        "errores": errores + errores_wiki,
    }


# ----------------------------------------------------------------------
# Análisis
# ----------------------------------------------------------------------

def analizar(entrada: str, progreso: Progreso | None = None, guardar: bool = True) -> dict:
    inicio = time.time()
    progreso = progreso or Progreso()
    cfg = config.obtener()
    ahora = datetime.now(timezone.utc)
    entrada = validar_entrada(entrada)
    advertencias: list[str] = []
    umbral_cob = float(config.valor(cfg, "similitud.cobertura", 0.25))
    umbral_fuerte = float(config.valor(cfg, "similitud.verificacion_fuerte", 0.35))
    umbral_rel = float(config.valor(cfg, "similitud.verificacion_relacionada", 0.2))

    internet = red.hay_internet()
    if not internet:
        advertencias.append("No hay conexión a internet: solo se revisaron el texto y las listas locales. "
                            "El resultado está incompleto.")

    # 1. Entrada ---------------------------------------------------------
    progreso.iniciar("entrada")
    fuentes: list[dict] = []
    if es_url(entrada) and not internet:
        url = normalizar_url(entrada)
        noticia = Noticia(tipo="url", url=url, dominio=dominio_de(url), titulo=_titulo_desde_url(url),
                          error_descarga="Sin conexión a internet: no se pudo descargar la página.",
                          tipo_error=red.SIN_INTERNET)
        noticia.idioma = texto.detectar_idioma(noticia.titulo)
    else:
        noticia = leer(entrada)
    if noticia.tipo == "url":
        fuentes.append({
            "nombre": "Descarga de la noticia", "estado": "error" if noticia.error_descarga and not noticia.tiene_texto else "ok",
            "mensaje": noticia.error_descarga or f"Se extrajo el texto ({len(noticia.cuerpo):,} caracteres).".replace(",", "."),
            "tipo_error": noticia.tipo_error, "consultas": [noticia.url], "cantidad": 1 if noticia.tiene_texto else 0,
            "desde_cache": False, "duracion": 0,
        })
        if noticia.error_descarga:
            advertencias.append(f"{noticia.error_descarga} Se analizó el sitio y la dirección; para un análisis "
                                "completo, pega el texto de la noticia.")
    if not noticia.titulo and not noticia.cuerpo:
        raise ErrorAnalisis(
            f"No se pudo leer la noticia. {noticia.error_descarga or ''} Copia el texto de la noticia y pégalo directamente."
        )
    progreso.terminar("entrada", texto.recortar(noticia.titulo, 90))

    # 2. Palabras clave ----------------------------------------------------
    progreso.iniciar("palabras")
    # El titular sin expresiones de "cadena" (urgente, compártelo...) para que no ensucien las búsquedas.
    gancho = (config.valor(cfg, "alertas.palabras_gancho", {}) or {})
    titulo_limpio = texto.quitar_expresiones(noticia.titulo, list(gancho.get("es") or []) + list(gancho.get("en") or []))
    titulo_limpio = nlp.limpiar_titular(titulo_limpio or noticia.titulo, max_palabras=40)
    consultas = nlp.preparar(titulo_limpio, noticia.cuerpo, noticia.idioma)
    referencia = noticia.referencia(titulo_limpio)
    progreso.terminar("palabras", ", ".join(consultas["terminos"][:6]))

    # 3. Búsquedas en paralelo --------------------------------------------
    progreso.iniciar("busquedas", "GDELT, Google News, DuckDuckGo y base de verificaciones")
    listas = dominios.listas()
    idioma = noticia.idioma
    consulta_gdelt = gdelt.armar_consulta(consultas["terminos_consulta"])
    tareas: dict[str, concurrent.futures.Future] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ejecutor:
        tareas["indice"] = ejecutor.submit(_buscar_en_indice, consultas["terminos"])
        if internet:
            tareas["gdelt"] = ejecutor.submit(gdelt.buscar, consulta_gdelt, idioma)
            tareas["google_news"] = ejecutor.submit(google_news.buscar, consultas["consulta"], idioma)
            tareas["duckduckgo"] = ejecutor.submit(duckduckgo.buscar_noticias, consultas["consulta_titular"], idioma)
            tareas["ddg_verificadores"] = ejecutor.submit(verificadores.buscar_en_duckduckgo, consultas["consulta"], idioma)
            if config.valor(cfg, "fuentes.gdelt.buscar_en_verificadores", True):
                tareas["gdelt_verificadores"] = ejecutor.submit(
                    gdelt.buscar_en_dominios, gdelt.armar_consulta(consultas["terminos_amplios"] or consultas["terminos_consulta"], 3),
                    listas.dominios_verificadores(idioma), idioma)
            if noticia.tipo == "url":
                tareas["antiguedad"] = ejecutor.submit(dominios.antiguedad, noticia.dominio)
        resultados = {clave: futuro.result() for clave, futuro in tareas.items()}
    antiguedad = resultados.pop("antiguedad", None)
    for clave in ("gdelt", "google_news", "duckduckgo"):
        if clave not in resultados:
            resultados[clave] = ResultadoFuente(
                nombre={"gdelt": "GDELT", "google_news": "Google News", "duckduckgo": "DuckDuckGo"}[clave],
                estado="error", tipo_error=red.SIN_INTERNET, mensaje=red.MENSAJES[red.SIN_INTERNET])
    de_cobertura = [resultados[c] for c in ("gdelt", "google_news", "duckduckgo")]
    articulos = _clasificar_articulos([a for r in de_cobertura for a in r.articulos], listas, referencia)
    respondieron = [r.nombre for r in de_cobertura if r.respondio]
    fallaron = [r.nombre for r in de_cobertura if not r.respondio and r.estado != "desactivada"]
    for r in de_cobertura:
        if r.estado == "error" and r.tipo_error == red.LIMITE:
            advertencias.append(f"{r.nombre}: {r.mensaje}")
    progreso.terminar("busquedas", f"{len(articulos)} artículos encontrados")

    # Separar la fuente original, los verificadores y la cobertura.
    clasif_fuente = listas.clasificar(noticia.url) if noticia.tipo == "url" else None
    def es_original(a: dict) -> bool:
        return bool(clasif_fuente) and (
            dominios.dominio_registrado(a.get("dominio", "")) == clasif_fuente.registrado
            or (a.get("grupo") and a.get("grupo") == clasif_fuente.grupo and clasif_fuente.categoria)
        )
    candidatos_verificador = [a for a in articulos if a["es_verificador"]]
    for clave in ("ddg_verificadores", "gdelt_verificadores"):
        if clave in resultados:
            candidatos_verificador += [a for a in _clasificar_articulos(resultados[clave].articulos, listas, referencia)
                                       if a["es_verificador"]]
    cobertura_util = [a for a in articulos if not a["es_verificador"] and not es_original(a)]
    # Artículos de medios que desmienten la noticia: no cuentan como "la publican".
    desmentidas_medios = [a for a in cobertura_util if a["desmiente"] and a["similitud"] >= umbral_rel]
    cobertura_util = [a for a in cobertura_util if not (a["desmiente"] and a["similitud"] >= umbral_rel)]
    coincidencias = [a for a in cobertura_util if a["similitud"] >= umbral_cob]
    relacionados = [a for a in cobertura_util if a["similitud"] < umbral_cob][:15]

    # 4. Verificadores ------------------------------------------------------
    progreso.iniciar("verificadores")
    lectura = verificadores.leer_paginas(candidatos_verificador, referencia) if internet else ResultadoFuente(
        nombre="Páginas de verificadores", estado="error", tipo_error=red.SIN_INTERNET, mensaje=red.MENSAJES[red.SIN_INTERNET])
    todas: list[dict] = []
    for v in noticia.claimreviews_en_pagina:
        todas.append({**v, "origen": "La página analizada", "similitud": 1.0, "de_la_pagina": True})
    todas += [{**v} for v in (resultados["indice"].extra.get("verificaciones") or [])]
    todas += [{**v} for v in (lectura.extra.get("verificaciones") or [])]
    unicas: dict[tuple, dict] = {}
    for v in todas:
        # La misma verificación puede venir de la base y de la página, o repetida con otra dirección.
        clave = (texto.normalizar(v.get("organizacion", ""))[:40], texto.normalizar(v.get("afirmacion", ""))[:120])
        if clave not in unicas or v.get("de_la_pagina"):
            unicas[clave] = v
    verificaciones_lista = list(unicas.values())
    afirmaciones = [v.get("afirmacion", "") for v in verificaciones_lista]
    coberturas = similitud.cobertura_ponderada(referencia, afirmaciones)
    sin_calcular = [v for v in verificaciones_lista if "similitud" not in v]
    for v, s in zip(sin_calcular, similitud.similitudes(referencia, [v.get("afirmacion", "") for v in sin_calcular])):
        v["similitud"] = s
    for v, c in zip(verificaciones_lista, coberturas):
        v["cobertura_palabras"] = 1.0 if v.get("de_la_pagina") else c
    verificaciones_lista = [claimreview.con_categoria(v) for v in verificaciones_lista]
    for v in verificaciones_lista:
        v["palabras_compartidas"] = similitud.palabras_compartidas(referencia, v.get("afirmacion", ""))
    verificaciones_lista.sort(key=lambda v: (v["similitud"] + v["cobertura_palabras"]) / 2, reverse=True)
    cobertura_min = float(config.valor(cfg, "similitud.verificacion_cobertura_minima", 0.6))

    def es_fuerte(v: dict) -> bool:
        return v["similitud"] >= umbral_fuerte and v["cobertura_palabras"] >= cobertura_min

    fuertes = [v for v in verificaciones_lista if es_fuerte(v)]
    relacionadas = [v for v in verificaciones_lista if not es_fuerte(v) and v["similitud"] >= umbral_rel][:8]
    sin_marcado = [a for a in (lectura.extra.get("sin_marcado") or []) if a.get("similitud", 0) >= umbral_rel]
    for a in desmentidas_medios:
        if a.get("categoria") == dominios.CONFIABLE:
            sin_marcado.append({**a, "veredicto_titulo": claimreview.veredicto_desde_titulo(a.get("titulo", ""))
                                or claimreview.FALSO, "medio_confiable": True})
    sin_marcado_relevantes = [a for a in sin_marcado if a.get("similitud", 0) >= umbral_cob]
    progreso.terminar("verificadores", f"{len(fuertes)} verificaciones coincidentes")

    # 5. Fuente y señales ----------------------------------------------------
    progreso.iniciar("fuente")
    fuente: dict = {}
    if noticia.tipo == "url" and clasif_fuente:
        fuente = clasif_fuente.a_dict()
        fuente["dominio"] = noticia.dominio
        fuente["imitacion"] = dominios.detectar_imitacion(noticia.dominio, listas)
        fuente["antiguedad"] = antiguedad or {"error": "No se consultó (sin conexión a internet)."}
    alertas = senales.detectar(noticia, cfg)
    vieja = _noticia_vieja(noticia, coincidencias, cfg, ahora)
    progreso.terminar("fuente", fuente.get("nombre_categoria", "Texto sin fuente") if fuente else "Texto sin fuente")

    # 6. Puntaje ------------------------------------------------------------
    progreso.iniciar("puntaje")
    evidencia = {
        "ahora": ahora.isoformat(),
        "noticia": {"tipo": noticia.tipo, "tiene_texto": noticia.tiene_texto, "dominio": noticia.dominio},
        "verificaciones": {"fuertes": fuertes, "relacionadas": relacionadas, "sin_marcado": sin_marcado_relevantes,
                           "pagina_es_verificacion": bool(noticia.claimreviews_en_pagina)},
        "cobertura": {"consultada": bool(respondieron), "fuentes_consultadas": respondieron,
                      "fuentes_fallidas": fallaron, "coincidencias": coincidencias},
        "fuente": fuente,
        "alertas": alertas,
        "fecha_noticia": noticia.fecha,
        "noticia_vieja": vieja,
    }
    resultado_puntaje = puntaje.calcular(evidencia, cfg)
    progreso.terminar("puntaje", f"{resultado_puntaje['puntaje']} - {resultado_puntaje['etiqueta']}")

    # 7. Contexto -----------------------------------------------------------
    contexto = None
    if resultado_puntaje["clave_etiqueta"] in ETIQUETAS_CONFIABLES and internet:
        progreso.iniciar("contexto")
        contexto = _contexto(noticia, coincidencias, consultas, referencia)
        progreso.terminar("contexto", f"{len(contexto['resumen'])} frases, {len(contexto['wikipedia'])} entradas de Wikipedia")
    else:
        progreso.omitir("contexto", "Solo se arma cuando la noticia resulta confiable")

    for r in [resultados["indice"], *de_cobertura, resultados.get("ddg_verificadores"),
              resultados.get("gdelt_verificadores"), lectura]:
        if r is None:
            continue
        datos = r.a_dict()
        datos.pop("articulos", None)
        datos.pop("extra", None)
        fuentes.append(datos)
    if antiguedad:
        fuentes.append({
            "nombre": f"Antigüedad del dominio ({antiguedad.get('metodo') or 'RDAP/WHOIS'})",
            "estado": "ok" if antiguedad.get("fecha_creacion") else "error",
            "mensaje": f"Creado el {antiguedad['fecha_creacion'][:10]}" if antiguedad.get("fecha_creacion") else antiguedad.get("error", ""),
            "consultas": [antiguedad["consulta"]] if antiguedad.get("consulta") else [],
            "cantidad": 1 if antiguedad.get("fecha_creacion") else 0,
            "desde_cache": antiguedad.get("desde_cache", False), "duracion": 0,
        })
    if contexto is not None:
        fuentes.append({
            "nombre": "Wikipedia", "estado": "ok" if contexto["wikipedia"] else "sin_resultados",
            "mensaje": "; ".join(contexto["errores"][:3]) or f"{len(contexto['wikipedia'])} resúmenes",
            "consultas": [w["url"] for w in contexto["wikipedia"]], "cantidad": len(contexto["wikipedia"]),
            "desde_cache": False, "duracion": 0,
        })

    resultado = {
        "version": 1,
        "fecha_analisis": ahora.isoformat(),
        "entrada": entrada,
        "noticia": noticia.a_dict(),
        "consultas": {k: consultas[k] for k in ("terminos", "consulta", "consulta_titular", "palabras_clave",
                                                 "entidades", "modelo_entidades")},
        "resultado": resultado_puntaje,
        "verificaciones": {"fuertes": fuertes[:10], "relacionadas": relacionadas, "sin_marcado": sin_marcado[:8]},
        "cobertura": {"coincidencias": coincidencias, "relacionados": relacionados,
                      "desmentidas_en_medios": desmentidas_medios[:8], "umbral": umbral_cob, "fuentes_consultadas": respondieron, "fuentes_fallidas": fallaron},
        "fuente": fuente,
        "alertas": alertas,
        "noticia_vieja": vieja,
        "contexto": contexto,
        "fuentes_consultadas": fuentes,
        "advertencias": advertencias + resultado_puntaje.get("avisos", []),
        "duracion_segundos": round(time.time() - inicio, 1),
    }
    if guardar:
        try:
            resultado["id"] = historial.guardar(resultado)
        except Exception as e:  # noqa: BLE001 - el historial nunca debe impedir ver el resultado
            resultado["advertencias"].append(f"No se pudo guardar en el historial: {e}")
    return resultado
