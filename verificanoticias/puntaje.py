"""Fórmula de puntaje: base + señales, con prioridad para los veredictos de verificadores.

Todos los pesos y umbrales están en la configuración (sección ``puntaje`` y
``etiquetas``). Esta función no consulta internet: recibe la evidencia ya
reunida y explica cada suma y cada resta.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from . import config
from .fuentes import claimreview as cr
from .fuentes.base import a_datetime

ETIQUETAS = {
    "confirmada": "Confirmada",
    "probablemente_verdadera": "Probablemente verdadera",
    "dudosa": "Dudosa",
    "probablemente_falsa": "Probablemente falsa",
    "desmentida": "Desmentida por verificadores",
    "sin_datos": "Sin datos suficientes",
}
EXPLICACIONES = {
    "confirmada": "Varios medios confiables e independientes publican lo mismo.",
    "probablemente_verdadera": "Hay señales a favor, pero no alcanzan para darla por confirmada.",
    "dudosa": "Las señales son mixtas o insuficientes. Conviene buscar más fuentes o esperar.",
    "probablemente_falsa": "Predominan las señales de alerta y falta el respaldo de medios confiables.",
    "desmentida": "Verificadores profesionales analizaron esta afirmación y la calificaron como falsa.",
    "sin_datos": "No se encontró información suficiente para opinar. Esto NO significa que sea falsa.",
}
GRUPOS = {
    "verificadores": "Verificadores profesionales",
    "corroboracion": "Cobertura en otros medios",
    "fuente": "Fuente original",
    "alertas": "Señales de alerta en el texto",
    "calidad": "Calidad del texto",
    "ajuste": "Ajuste",
}


@dataclass
class Senal:
    grupo: str
    clave: str
    titulo: str
    detalle: str
    puntos: float = 0
    evidencias: list[dict] = field(default_factory=list)
    informativa: bool = False

    def a_dict(self) -> dict:
        datos = asdict(self)
        datos["nombre_grupo"] = GRUPOS.get(self.grupo, self.grupo)
        return datos


def _links(items: list[dict], maximo: int = 8) -> list[dict]:
    vistos, links = set(), []
    for item in items:
        url = item.get("url")
        if url and url not in vistos:
            vistos.add(url)
            etiqueta = item.get("titulo") or item.get("afirmacion") or url
            medio = item.get("medio") or item.get("organizacion") or item.get("dominio") or ""
            links.append({"titulo": etiqueta, "url": url, "medio": medio, "fecha": item.get("fecha")})
        if len(links) >= maximo:
            break
    return links


def _fecha_corta(iso: str | None) -> str:
    fecha = a_datetime(iso)
    return fecha.strftime("%d/%m/%Y") if fecha else "fecha desconocida"


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def calcular(evidencia: dict, cfg: dict | None = None) -> dict:
    cfg = cfg or config.obtener()
    p = config.valor(cfg, "puntaje", {})
    umbrales = config.valor(cfg, "etiquetas", {})
    ahora = a_datetime(evidencia.get("ahora")) or datetime.now(timezone.utc)
    senales: list[Senal] = []
    avisos: list[str] = []

    noticia = evidencia.get("noticia") or {}
    alertas = evidencia.get("alertas") or {}
    cobertura = evidencia.get("cobertura") or {}
    fuente = evidencia.get("fuente") or {}
    verif = evidencia.get("verificaciones") or {}

    # ------------------------------------------------------------------
    # A. Corroboración: ¿quién más lo publica?
    # ------------------------------------------------------------------
    pc = p["corroboracion"]
    coincidencias = cobertura.get("coincidencias") or []
    confiables = [a for a in coincidencias if a.get("categoria") == "confiable"]
    sin_clasificar = [a for a in coincidencias if not a.get("categoria")]
    dudosos = [a for a in coincidencias if a.get("categoria") in ("desinformacion", "satira")]
    grupos_confiables = sorted({a.get("grupo") or a.get("dominio") for a in confiables})
    dominios_sin_clasificar = sorted({a.get("dominio") for a in sin_clasificar if a.get("dominio")})
    dominios_dudosos = sorted({a.get("dominio") for a in dudosos if a.get("dominio")})

    puntos_confiables = min(len(grupos_confiables) * pc["por_medio_confiable"], pc["max_medios_confiables"])
    puntos_sc = min(len(dominios_sin_clasificar) * pc["por_medio_sin_clasificar"], pc["max_medios_sin_clasificar"])
    puntos_sc = max(0, min(puntos_sc, pc["tope_positivo"] - puntos_confiables))
    if grupos_confiables:
        senales.append(Senal(
            "corroboracion", "medios_confiables",
            f"La publican {_plural(len(grupos_confiables), 'medio confiable independiente', 'medios confiables independientes')}",
            f"Medios: {', '.join(sorted({a.get('medio') or a.get('dominio') for a in confiables}))}. "
            f"Cada grupo editorial cuenta una sola vez (+{pc['por_medio_confiable']} c/u, máximo +{pc['max_medios_confiables']}).",
            puntos_confiables, _links(confiables),
        ))
    if dominios_sin_clasificar:
        senales.append(Senal(
            "corroboracion", "medios_sin_clasificar",
            f"También la publican {_plural(len(dominios_sin_clasificar), 'sitio sin clasificar', 'sitios sin clasificar')}",
            f"Sitios que no están en ninguna lista: {', '.join(dominios_sin_clasificar[:8])}. Suman poco porque no se conoce su confiabilidad.",
            puntos_sc, _links(sin_clasificar),
        ))
    if dominios_dudosos:
        puntos = max(len(dominios_dudosos) * pc["por_sitio_desinformacion"], pc["max_sitios_desinformacion"])
        senales.append(Senal(
            "corroboracion", "sitios_dudosos",
            f"La difunden {_plural(len(dominios_dudosos), 'sitio poco confiable o de humor', 'sitios poco confiables o de humor')}",
            f"Sitios: {', '.join(dominios_dudosos)}.", puntos, _links(dudosos),
        ))

    alto_impacto = alertas.get("alto_impacto") or []
    fallidas = cobertura.get("fuentes_fallidas") or []
    consultadas = cobertura.get("fuentes_consultadas") or []
    horas = None
    fecha_noticia = a_datetime(evidencia.get("fecha_noticia"))
    if fecha_noticia:
        horas = (ahora - fecha_noticia).total_seconds() / 3600
    reciente = horas is not None and horas <= pc["horas_reciente"]
    if cobertura.get("consultada") and not grupos_confiables:
        donde = ", ".join(consultadas) or "los buscadores"
        if alto_impacto:
            if horas is None:
                puntos, cuando = pc["sin_cobertura_alto_impacto_fecha_desconocida"], "No se conoce la fecha de la noticia."
            elif reciente:
                puntos, cuando = pc["sin_cobertura_alto_impacto_reciente"], f"La noticia tiene menos de {pc['horas_reciente']} horas: puede que todavía no la hayan publicado."
            else:
                puntos, cuando = pc["sin_cobertura_alto_impacto_vieja"], f"La noticia tiene más de {pc['horas_reciente']} horas."
            senales.append(Senal(
                "corroboracion", "sin_cobertura_alto_impacto",
                "Afirmación de gran impacto que ningún medio confiable publica",
                f"El texto habla de algo importante ({', '.join(alto_impacto[:5])}), pero en {donde} no aparece en "
                f"ningún medio confiable. Algo así normalmente sería noticia en todos lados. {cuando} "
                "Ojo: esto es falta de confirmación, no una prueba de que sea falsa.",
                puntos,
            ))
        else:
            senales.append(Senal(
                "corroboracion", "sin_cobertura",
                "Ningún medio confiable publica algo parecido",
                f"Se buscó en {donde}. No encontrar confirmación no prueba que sea falsa: puede ser muy reciente, local o poco conocida.",
                pc["sin_cobertura_normal"],
            ))
        if reciente:
            avisos.append("La noticia es muy reciente: es posible que los medios todavía no la hayan publicado. "
                          "Vuelve a analizarla en unas horas.")
    elif not cobertura.get("consultada"):
        senales.append(Senal(
            "corroboracion", "cobertura_no_consultada", "No se pudo buscar la noticia en otros medios",
            f"Fallaron las búsquedas ({', '.join(fallidas) or 'sin conexión'}). Por eso la falta de cobertura no se cuenta.",
            0, informativa=True,
        ))

    # ------------------------------------------------------------------
    # B. Fuente original
    # ------------------------------------------------------------------
    pf = p["fuente"]
    if noticia.get("tipo") == "url":
        dominio = fuente.get("dominio", "")
        categoria = fuente.get("categoria")
        origen = f" (según {fuente['origen']})" if fuente.get("origen") else ""
        detalle_extra = f" {fuente['detalle']}." if fuente.get("detalle") else ""
        if categoria == "confiable":
            senales.append(Senal("fuente", "fuente_confiable", f"{dominio} es un medio confiable",
                                 f"Figura en la lista de medios confiables{origen}.{detalle_extra}", pf["medio_confiable"]))
        elif categoria == "verificador":
            senales.append(Senal("fuente", "fuente_verificador", f"{dominio} es un verificador de datos",
                                 f"Figura en la lista de verificadores{origen}.", pf["verificador"]))
        elif categoria == "desinformacion":
            senales.append(Senal("fuente", "fuente_desinformacion", f"{dominio} es un sitio poco confiable",
                                 f"Figura en la lista de desinformación{origen}.{detalle_extra}", pf["desinformacion"]))
        elif categoria == "satira":
            senales.append(Senal("fuente", "fuente_satira", f"{dominio} es un sitio de humor",
                                 f"Publica noticias inventadas a propósito, como humor{origen}.", pf["satira"]))
            avisos.append(f"{dominio} es un sitio satírico: sus «noticias» son humor, no hechos reales.")
        else:
            senales.append(Senal("fuente", "fuente_desconocida", f"{dominio} no está en ninguna lista",
                                 "No se sabe si es confiable. Puedes agregarlo a tus listas si lo conoces.", 0, informativa=True))
        antig = fuente.get("antiguedad") or {}
        dias = antig.get("dias")
        imitacion = fuente.get("imitacion")
        if imitacion:
            antiguo = dias is not None and dias > 5 * 365
            senales.append(Senal(
                "fuente", "imitacion", f"El dominio parece imitar a {imitacion['imita']}",
                f"{imitacion['motivo']}."
                + (" Como el dominio tiene más de 5 años, la resta es menor: puede ser un sitio distinto y legítimo."
                   if antiguo else " Es una técnica habitual de los sitios que difunden noticias falsas."),
                pf["imitacion_dominio_antiguo"] if antiguo else pf["imitacion"],
            ))
        consulta = [{"titulo": f"Consulta {antig.get('metodo') or 'RDAP'} de {antig.get('dominio', dominio)}",
                     "url": antig["consulta"]}] if antig.get("consulta") else []
        if dias is not None:
            creado = _fecha_corta(antig.get("fecha_creacion"))
            if dias < 180:
                senales.append(Senal("fuente", "dominio_nuevo", "Dominio creado hace menos de 6 meses",
                                     f"Registrado el {creado} (hace {dias} días). Los sitios de desinformación suelen ser nuevos.",
                                     pf["dominio_menor_6_meses"], consulta))
            elif dias < 730:
                senales.append(Senal("fuente", "dominio_reciente", "Dominio con menos de 2 años",
                                     f"Registrado el {creado}.", pf["dominio_menor_2_anios"], consulta))
            elif dias > 5 * 365:
                senales.append(Senal("fuente", "dominio_antiguo", "Dominio con más de 5 años",
                                     f"Registrado el {creado}.", pf["dominio_mayor_5_anios"], consulta))
            else:
                senales.append(Senal("fuente", "dominio_edad_media", "Dominio de entre 2 y 5 años",
                                     f"Registrado el {creado}.", 0, consulta, informativa=True))
        elif antig.get("error"):
            senales.append(Senal("fuente", "dominio_sin_fecha", "No se pudo saber la antigüedad del dominio",
                                 antig["error"], 0, consulta, informativa=True))
    else:
        senales.append(Senal("fuente", "sin_fuente", "No se indicó la fuente original",
                             "Se analizó texto pegado. Si tienes el link de la noticia, analízalo: permite evaluar el sitio.",
                             0, informativa=True))

    # ------------------------------------------------------------------
    # C. Señales de alerta
    # ------------------------------------------------------------------
    pa = p["alertas"]
    alertas_senales: list[Senal] = []
    may = alertas.get("mayusculas") or {}
    if may.get("detectada"):
        alertas_senales.append(Senal("alertas", "mayusculas", "Uso exagerado de MAYÚSCULAS",
                                     f"Ejemplos: {', '.join(may.get('ejemplos') or [])}.", pa["mayusculas"]))
    exc = alertas.get("exclamaciones") or {}
    if exc.get("detectada"):
        alertas_senales.append(Senal("alertas", "exclamaciones", "Muchos signos de exclamación",
                                     f"{exc.get('en_titulo', 0)} en el titular y {exc.get('en_texto', 0)} en el texto.",
                                     pa["exclamaciones"]))
    gancho = alertas.get("palabras_gancho") or []
    if gancho:
        alertas_senales.append(Senal("alertas", "palabras_gancho", "Lenguaje sensacionalista o de «cadena»",
                                     f"Expresiones encontradas: {', '.join(gancho)}.",
                                     max(len(gancho) * pa["palabra_gancho"], pa["max_palabras_gancho"])))
    autor = alertas.get("autor") or {}
    if autor.get("evaluado") and not autor.get("valor"):
        alertas_senales.append(Senal("alertas", "sin_autor", "No figura el autor", "La página no indica quién escribió la nota.", pa["sin_autor"]))
    fecha = alertas.get("fecha") or {}
    if fecha.get("evaluado") and not fecha.get("valor"):
        alertas_senales.append(Senal("alertas", "sin_fecha", "No figura la fecha", "La página no indica cuándo se publicó.", pa["sin_fecha"]))
    citadas = alertas.get("fuentes_citadas") or {}
    if citadas.get("evaluado") and citadas.get("cantidad", 0) == 0:
        alertas_senales.append(Senal("alertas", "sin_fuentes", "No cita fuentes",
                                     "El texto no dice de dónde sale la información (no hay «según», declaraciones ni citas).",
                                     pa["sin_fuentes_citadas"]))
    vieja = evidencia.get("noticia_vieja") or {}
    if vieja.get("detectada"):
        alertas_senales.append(Senal("alertas", "noticia_vieja", "Posible noticia vieja presentada como nueva",
                                     vieja.get("motivo", ""), pa["noticia_vieja"], vieja.get("evidencias") or []))
    tc = alertas.get("titular_cuerpo") or {}
    if tc.get("detectada"):
        alertas_senales.append(Senal("alertas", "titular_no_coincide", "El titular no coincide con el texto",
                                     f"Solo el {int((tc.get('proporcion') or 0) * 100)}% de las palabras importantes del titular aparecen en el texto.",
                                     pa["titular_no_coincide"]))
    suma_alertas = sum(s.puntos for s in alertas_senales)
    if suma_alertas < pa["tope"]:
        exceso = pa["tope"] - suma_alertas
        alertas_senales.append(Senal("alertas", "tope_alertas", "Tope de señales de alerta",
                                     f"Las alertas no pueden restar más de {abs(pa['tope'])} puntos en total.", exceso))
        suma_alertas = pa["tope"]
    senales.extend(alertas_senales)

    # ------------------------------------------------------------------
    # D. Calidad
    # ------------------------------------------------------------------
    pq = p["calidad"]
    calidad: list[Senal] = []
    if citadas.get("evaluado") and citadas.get("cantidad", 0) >= 2:
        detalle = ", ".join(citadas.get("atribuciones") or [])
        if citadas.get("citas_textuales"):
            detalle = (detalle + ", " if detalle else "") + f"{citadas['citas_textuales']} cita(s) textual(es)"
        calidad.append(Senal("calidad", "cita_fuentes", "Cita fuentes", f"Encontrado: {detalle}.", pq["cita_fuentes"]))
    if autor.get("evaluado") and autor.get("valor") and fecha.get("valor"):
        calidad.append(Senal("calidad", "autor_y_fecha", "Indica autor y fecha",
                             f"Autor: {autor['valor']}. Fecha: {_fecha_corta(fecha['valor'])}.", pq["autor_y_fecha"]))
    suma_calidad = sum(s.puntos for s in calidad)
    if suma_calidad > pq["tope"]:
        calidad.append(Senal("calidad", "tope_calidad", "Tope de calidad", f"La calidad suma como máximo {pq['tope']}.",
                             pq["tope"] - suma_calidad))
    senales.extend(calidad)

    # ------------------------------------------------------------------
    # Artículos de verificadores sin marcado ClaimReview
    # ------------------------------------------------------------------
    pv = p["verificadores"]
    sin_marcado = verif.get("sin_marcado") or []
    falsos_titulo = [a for a in sin_marcado if a.get("veredicto_titulo") in (cr.FALSO, cr.ENGANOSO)]
    fuertes = [v for v in (verif.get("fuertes") or []) if v.get("categoria") != cr.DESCONOCIDO]
    fechas_confiables = [d for a in confiables if (d := a_datetime(a.get("fecha")))]
    if falsos_titulo and len(grupos_confiables) >= 2 and fechas_confiables:
        # Desmentidos anteriores a la cobertura actual: puede ser un hecho nuevo.
        anteriores = [a for a in falsos_titulo if (d := a_datetime(a.get("fecha"))) and d < max(fechas_confiables)]
        if anteriores:
            senales.append(Senal(
                "verificadores", "desmentido_anterior", "Hubo un desmentido anterior a la cobertura actual",
                f"Un artículo del {_fecha_corta(anteriores[0].get('fecha'))} decía que era falsa, pero medios confiables "
                "la publican después. Puede ser un rumor viejo que ahora sí ocurrió: no se resta, pero revisa las fechas.",
                0, _links(anteriores), informativa=True,
            ))
            falsos_titulo = [a for a in falsos_titulo if a not in anteriores]
    if falsos_titulo and not fuertes:
        senales.append(Senal(
            "verificadores", "verificador_titulo_falso", "Un verificador o medio confiable publicó que es falsa",
            "El título del artículo indica que es falsa o engañosa, pero la página no tiene un veredicto estructurado "
            "(ClaimReview), así que no se aplica como veredicto oficial. Lee el artículo para confirmarlo.",
            pv["articulo_verificador_sin_claimreview_falso"], _links(falsos_titulo),
        ))

    # ------------------------------------------------------------------
    # Suma
    # ------------------------------------------------------------------
    base = p["base"]
    total = base + sum(s.puntos for s in senales)
    puntaje = max(0, min(100, round(total)))
    if puntaje != round(total):
        senales.append(Senal(
            "ajuste", "limite", "El puntaje se limita entre 0 y 100",
            f"La suma dio {round(total)}; el puntaje no puede ser menor que 0 ni mayor que 100.",
            puntaje - round(total), informativa=True,
        ))
    clave_etiqueta: str | None = None
    veredicto_aplicado = None

    # ------------------------------------------------------------------
    # Veredictos de verificadores (tienen prioridad)
    # ------------------------------------------------------------------
    if fuertes:
        categorias = {v["categoria"] for v in fuertes}
        negativos = [v for v in fuertes if v["categoria"] in cr.NEGATIVOS]
        positivos = [v for v in fuertes if v["categoria"] in cr.POSITIVOS]
        # ¿Medios confiables la publicaron DESPUÉS de la verificación negativa? Puede ser un hecho nuevo
        # (por ejemplo, un rumor desmentido hace años que ahora sí ocurrió).
        fechas_negativas = [d for v in negativos if (d := a_datetime(v.get("fecha")))]
        posterior = bool(fechas_confiables) and (
            len(fechas_negativas) < len(negativos) or max(fechas_confiables) > max(fechas_negativas)
        )
        links = _links(fuertes)
        if negativos and positivos:
            clave_etiqueta = "dudosa"
            nuevo = min(max(puntaje, umbrales["dudosa"]), umbrales["probablemente_verdadera"] - 1)
            senales.append(Senal("verificadores", "veredictos_contradictorios", "Los verificadores no coinciden",
                                 "Hay verificaciones que la califican como falsa o engañosa y otras como verdadera. "
                                 "Revisa cada una: pueden referirse a afirmaciones parecidas pero distintas.",
                                 nuevo - puntaje, links))
            puntaje = nuevo
            veredicto_aplicado = "contradictorio"
        elif negativos and len(grupos_confiables) >= 2 and posterior:
            clave_etiqueta = "dudosa"
            nuevo = min(max(puntaje, umbrales["dudosa"]), umbrales["probablemente_verdadera"] - 1)
            primera = negativos[0]
            senales.append(Senal(
                "verificadores", "verificacion_antigua", "Un verificador la desmintió, pero medios confiables la publican después",
                f"{primera.get('organizacion') or 'Un verificador'} la calificó como «{primera.get('veredicto')}» "
                f"({_fecha_corta(primera.get('fecha'))}), pero {len(grupos_confiables)} medios confiables publican algo "
                f"parecido con fecha posterior ({_fecha_corta(max(fechas_confiables).isoformat())}). Puede tratarse de un hecho "
                "nuevo (por ejemplo, un rumor desmentido hace tiempo que ahora sí ocurrió). Revisa las fechas y los artículos.",
                nuevo - puntaje, links,
            ))
            puntaje = nuevo
            veredicto_aplicado = "antiguo"
        elif negativos:
            orden = [cr.FALSO, cr.ENGANOSO, cr.SATIRA, cr.SIN_EVIDENCIA]
            peor = min(negativos, key=lambda v: orden.index(v["categoria"]))
            topes = {cr.FALSO: pv["falso_tope"], cr.ENGANOSO: pv["enganoso_tope"],
                     cr.SIN_EVIDENCIA: pv["sin_evidencia_tope"], cr.SATIRA: pv["satira_tope"]}
            tope = topes[peor["categoria"]]
            nuevo = min(puntaje, tope)
            senales.append(Senal(
                "verificadores", f"veredicto_{peor['categoria']}",
                f"{peor.get('organizacion') or 'Un verificador'}: «{peor.get('veredicto') or cr.NOMBRES[peor['categoria']]}»",
                f"Veredicto oficial ({cr.NOMBRES[peor['categoria']]}). Tiene prioridad sobre las demás señales: "
                f"el puntaje no puede superar {tope}.",
                nuevo - puntaje, links,
            ))
            puntaje = nuevo
            veredicto_aplicado = peor["categoria"]
            if peor["categoria"] == cr.FALSO:
                clave_etiqueta = "desmentida"
        elif positivos:
            mejor = cr.VERDADERO if any(v["categoria"] == cr.VERDADERO for v in positivos) else cr.MAYORMENTE_VERDADERO
            minimo = pv["verdadero_minimo"] if mejor == cr.VERDADERO else pv["mayormente_verdadero_minimo"]
            elegido = next(v for v in positivos if v["categoria"] == mejor)
            nuevo = max(puntaje, minimo)
            senales.append(Senal(
                "verificadores", f"veredicto_{mejor}",
                f"{elegido.get('organizacion') or 'Un verificador'}: «{elegido.get('veredicto') or cr.NOMBRES[mejor]}»",
                f"Veredicto oficial ({cr.NOMBRES[mejor]}). Tiene prioridad: el puntaje no puede bajar de {minimo}.",
                nuevo - puntaje, links,
            ))
            puntaje = nuevo
            veredicto_aplicado = mejor
            if mejor == cr.VERDADERO:
                clave_etiqueta = "confirmada"
        if categorias - {cr.DESCONOCIDO} and verif.get("pagina_es_verificacion"):
            avisos.append("El link analizado es una verificación: el veredicto se refiere a la afirmación que revisa el verificador.")

    # ------------------------------------------------------------------
    # Etiqueta
    # ------------------------------------------------------------------
    motivo_sin_datos = None
    if clave_etiqueta is None:
        antig_dias = (fuente.get("antiguedad") or {}).get("dias")
        evidencia_externa = bool(
            fuertes or falsos_titulo or coincidencias or fuente.get("categoria") or fuente.get("imitacion")
            or (antig_dias is not None and antig_dias < 730)
        )
        if not cobertura.get("consultada") and not evidencia_externa:
            motivo_sin_datos = "No se pudo consultar ninguna fuente de búsqueda y no hay otra evidencia."
        elif not evidencia_externa and not alto_impacto and abs(suma_alertas) < umbrales["alertas_minimas_para_opinar"]:
            motivo_sin_datos = ("No se encontraron verificaciones, ni cobertura en otros medios, ni señales de alerta "
                                "importantes. No hay base para opinar en ningún sentido.")
        if motivo_sin_datos:
            clave_etiqueta = "sin_datos"
        elif puntaje >= umbrales["confirmada"] and len(grupos_confiables) >= umbrales["medios_para_confirmar"]:
            clave_etiqueta = "confirmada"
        elif puntaje >= umbrales["probablemente_verdadera"]:
            clave_etiqueta = "probablemente_verdadera"
            if puntaje >= umbrales["confirmada"]:
                avisos.append(f"Para «Confirmada» hacen falta al menos {umbrales['medios_para_confirmar']} medios "
                              "confiables independientes que la publiquen.")
        elif puntaje >= umbrales["dudosa"]:
            clave_etiqueta = "dudosa"
        else:
            clave_etiqueta = "probablemente_falsa"

    explicacion = EXPLICACIONES[clave_etiqueta]
    if motivo_sin_datos:
        explicacion = f"{explicacion} {motivo_sin_datos}"
    if veredicto_aplicado and veredicto_aplicado not in ("contradictorio", "antiguo") and clave_etiqueta != "desmentida":
        explicacion = f"Un verificador la calificó como «{cr.NOMBRES[veredicto_aplicado]}». {explicacion}"

    return {
        "puntaje": puntaje,
        "puntaje_sin_limites": round(total, 1),
        "base": base,
        "clave_etiqueta": clave_etiqueta,
        "etiqueta": ETIQUETAS[clave_etiqueta],
        "explicacion": explicacion,
        "veredicto_aplicado": veredicto_aplicado,
        "medios_confiables_independientes": len(grupos_confiables),
        "senales": [s.a_dict() for s in senales],
        "avisos": avisos,
    }
