"""Clasificación de dominios: listas locales, imitaciones y antigüedad (RDAP/WHOIS)."""

from __future__ import annotations

import concurrent.futures
import csv
import io
import threading
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import tldextract

from . import cache, config, red, texto
from .fuentes.base import a_datetime, dominio_de, fecha_iso

CONFIABLE = "confiable"
VERIFICADOR = "verificador"
DESINFORMACION = "desinformacion"
SATIRA = "satira"

NOMBRES_CATEGORIA = {
    CONFIABLE: "Medio confiable",
    VERIFICADOR: "Verificador de datos",
    DESINFORMACION: "Sitio poco confiable / desinformación",
    SATIRA: "Sitio de humor / sátira",
    None: "Sin clasificar",
}

ARCHIVOS_MANUALES = {
    "medios_confiables.csv": CONFIABLE,
    "verificadores.csv": VERIFICADOR,
    "desinformacion.csv": DESINFORMACION,
    "satira.csv": SATIRA,
}

# Palabras en la dirección que suelen indicar una sección de verificación.
PALABRAS_URL_VERIFICACION = ("fact-check", "factcheck", "fact_check", "verificacion", "verificado", "chequeo",
                             "el-detector", "eldetector", "bulo", "hoax", "verifica", "desinformacion",
                             "chequeado", "fake-news", "falso")

_extractor = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


def partes_dominio(host: str) -> tldextract.tldextract.ExtractResult:
    return _extractor(host)


def dominio_registrado(host: str) -> str:
    ext = partes_dominio(host)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return host


@dataclass
class Entrada:
    dominio: str
    ruta: str = ""
    categoria: str | None = None
    nombre: str = ""
    pais: str = ""
    idioma: str = ""
    grupo: str = ""
    detalle: str = ""
    origen: str = ""
    manual: bool = True


@dataclass
class Clasificacion:
    host: str
    registrado: str
    categoria: str | None = None
    nombre: str = ""
    grupo: str = ""
    origen: str = ""
    detalle: str = ""
    es_verificador: bool = False
    otras: list[dict] = field(default_factory=list)

    @property
    def nombre_categoria(self) -> str:
        return NOMBRES_CATEGORIA.get(self.categoria, "Sin clasificar")

    def a_dict(self) -> dict:
        datos = asdict(self)
        datos["nombre_categoria"] = self.nombre_categoria
        return datos


def _leer_csv(ruta: Path) -> list[dict]:
    """Lee un CSV tolerando los formatos que genera Excel (";" y codificación de Windows)."""
    try:
        contenido = ruta.read_bytes()
    except OSError:
        return []
    for codificacion in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto_csv = contenido.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    primera = texto_csv.split("\n", 1)[0]
    separador = ";" if primera.count(";") > primera.count(",") else ","
    lector = csv.DictReader(io.StringIO(texto_csv), delimiter=separador)
    filas = []
    for fila in lector:
        limpia = {(k or "").strip().lower(): (v or "").strip() for k, v in fila.items() if k}
        if limpia.get("dominio") and not limpia["dominio"].startswith("#"):
            filas.append(limpia)
    return filas


def _separar(dominio_con_ruta: str) -> tuple[str, str]:
    valor = dominio_con_ruta.strip().lower()
    if "//" in valor:
        partes = urlparse(valor)
        return dominio_de(partes.netloc), partes.path.rstrip("/")
    if "/" in valor:
        host, ruta = valor.split("/", 1)
        return dominio_de(host), "/" + ruta.rstrip("/")
    return dominio_de(valor), ""


class Listas:
    def __init__(self) -> None:
        self.manuales: dict[str, list[Entrada]] = {}
        self.importadas: dict[str, list[Entrada]] = {}
        self.cantidades: dict[str, int] = {}

    def _agregar(self, destino: dict, entrada: Entrada) -> None:
        destino.setdefault(entrada.dominio, []).append(entrada)

    @classmethod
    def cargar(cls, carpeta_manual: Path | None = None, carpeta_importada: Path | None = None) -> "Listas":
        listas = cls()
        carpeta_manual = carpeta_manual or config.ruta_listas()
        carpeta_importada = carpeta_importada or config.ruta_listas_importadas()
        for archivo, categoria in ARCHIVOS_MANUALES.items():
            filas = _leer_csv(carpeta_manual / archivo)
            listas.cantidades[archivo] = len(filas)
            for fila in filas:
                dominio, ruta = _separar(fila["dominio"])
                listas._agregar(listas.manuales, Entrada(
                    dominio=dominio, ruta=ruta, categoria=categoria, nombre=fila.get("nombre", ""),
                    pais=fila.get("pais", ""), idioma=fila.get("idioma", "").lower(),
                    grupo=(fila.get("grupo") or "").strip().lower(),
                    detalle=fila.get("motivo") or fila.get("nota") or "",
                    origen=f"tu lista {archivo}", manual=True,
                ))
        # Importadas, en orden de prioridad (la primera que tenga el dominio gana).
        for fila in _leer_csv(carpeta_importada / "domain_quality.csv"):
            dominio, ruta = _separar(fila["dominio"])
            listas._agregar(listas.importadas, Entrada(
                dominio=dominio, ruta=ruta, categoria=fila.get("categoria") or None,
                detalle=f"puntaje de calidad {fila.get('puntaje', '?')} (de 0 a 1)",
                origen="lista pública domain-quality-ratings (Lin et al. 2023)", manual=False,
            ))
        for fila in _leer_csv(carpeta_importada / "opensources.csv"):
            dominio, ruta = _separar(fila["dominio"])
            if dominio in listas.importadas:
                continue
            listas._agregar(listas.importadas, Entrada(
                dominio=dominio, ruta=ruta, categoria=fila.get("categoria") or None,
                detalle=f"tipo: {fila.get('tipo', '')}", origen="lista pública OpenSources (2017)", manual=False,
            ))
        for fila in _leer_csv(carpeta_importada / "verificadores_feed.csv"):
            dominio, ruta = _separar(fila["dominio"])
            if dominio in listas.importadas:
                continue
            listas._agregar(listas.importadas, Entrada(
                dominio=dominio, ruta=ruta, categoria=VERIFICADOR, nombre=fila.get("nombre", ""),
                detalle=f"{fila.get('verificaciones_en_feed', '?')} verificaciones en el feed ClaimReview",
                origen="feed ClaimReview (publica verificaciones)", manual=False,
            ))
        listas.cantidades["importadas"] = sum(len(v) for v in listas.importadas.values())
        return listas

    @staticmethod
    def _candidatos_host(host: str) -> list[str]:
        """clarin.com.ar → [clarin.com.ar]; a.b.efe.com → [a.b.efe.com, b.efe.com, efe.com]."""
        registrado = dominio_registrado(host)
        candidatos = [host]
        partes = host.split(".")
        for i in range(1, len(partes)):
            sufijo = ".".join(partes[i:])
            if len(sufijo) < len(registrado):
                break
            candidatos.append(sufijo)
        return list(dict.fromkeys(candidatos))

    def _buscar(self, tabla: dict, host: str, ruta_url: str) -> list[Entrada]:
        encontradas: list[tuple[int, Entrada]] = []
        for candidato in self._candidatos_host(host):
            for entrada in tabla.get(candidato, []):
                if entrada.ruta and not ruta_url.lower().startswith(entrada.ruta):
                    continue
                especificidad = len(candidato) * 10 + len(entrada.ruta)
                encontradas.append((especificidad, entrada))
        encontradas.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in encontradas]

    def clasificar(self, url_o_host: str) -> Clasificacion:
        valor = url_o_host.strip()
        if "//" not in valor and "/" in valor:
            valor = "//" + valor
        partes = urlparse(valor if "//" in valor else f"//{valor}")
        host = dominio_de(partes.netloc or valor)
        ruta_url = partes.path or ""
        registrado = dominio_registrado(host)
        clasif = Clasificacion(host=host, registrado=registrado, grupo=registrado)
        manuales = self._buscar(self.manuales, host, ruta_url)
        importadas = self._buscar(self.importadas, host, ruta_url)
        principal = manuales[0] if manuales else (importadas[0] if importadas else None)
        if principal:
            clasif.categoria = principal.categoria
            clasif.nombre = principal.nombre
            clasif.grupo = principal.grupo or registrado
            clasif.origen = principal.origen
            clasif.detalle = principal.detalle
        todas = manuales + importadas
        clasif.otras = [{"categoria": e.categoria, "origen": e.origen} for e in todas[1:4]]
        ruta_normalizada = ruta_url.lower()
        clasif.es_verificador = any(e.categoria == VERIFICADOR for e in todas) or any(
            p in ruta_normalizada for p in PALABRAS_URL_VERIFICACION
        )
        return clasif

    def marcas(self) -> list[tuple[str, str, str]]:
        """Medios reales que pueden ser imitados: (nombre_en_dominio, dominio, nombre)."""
        marcas = []
        for dominio, entradas in self.manuales.items():
            for entrada in entradas:
                if entrada.categoria in (CONFIABLE, VERIFICADOR) and not entrada.ruta:
                    ext = partes_dominio(dominio)
                    if ext.domain:
                        marcas.append((ext.domain, dominio, entrada.nombre or dominio))
                    break
        return marcas

    def dominios_verificadores(self, idioma: str) -> list[str]:
        """Dominios completos (sin secciones) de verificadores en ese idioma."""
        resultado = []
        for dominio, entradas in self.manuales.items():
            for e in entradas:
                if e.categoria == VERIFICADOR and not e.ruta and (not e.idioma or idioma in e.idioma):
                    resultado.append(dominio)
                    break
        return resultado

    def dominios_de_categoria(self, categoria: str, solo_manuales: bool = True) -> list[str]:
        tablas = [self.manuales] if solo_manuales else [self.manuales, self.importadas]
        resultado = []
        for tabla in tablas:
            for dominio, entradas in tabla.items():
                if any(e.categoria == categoria for e in entradas):
                    resultado.append(dominio)
        return resultado


_listas: Listas | None = None
_listas_lock = threading.Lock()


def listas() -> Listas:
    global _listas
    with _listas_lock:
        if _listas is None:
            _listas = Listas.cargar()
        return _listas


def recargar_listas() -> Listas:
    global _listas
    with _listas_lock:
        _listas = Listas.cargar()
        return _listas


# ----------------------------------------------------------------------
# Imitaciones
# ----------------------------------------------------------------------

_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ԁ": "d",
    "ɡ": "g", "ո": "n", "ս": "u", "ı": "i", "ⅼ": "l", "ӏ": "l", "ν": "v", "к": "k", "м": "m", "т": "t",
    "0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "$": "s", "@": "a",
})


def _decodificar(nombre: str) -> str:
    if nombre.startswith("xn--"):
        try:
            return nombre.encode("ascii").decode("idna")
        except UnicodeError:
            return nombre
    return nombre


def esqueleto(nombre: str) -> str:
    """Forma "visual" de un nombre: c1arín, clarіn (cirílico) y clarin dan lo mismo."""
    nombre = _decodificar(nombre.lower()).translate(_CONFUSABLES)
    nombre = "".join(c for c in unicodedata.normalize("NFKD", nombre) if not unicodedata.combining(c))
    nombre = nombre.replace("rn", "m").replace("vv", "w").replace("-", "").replace("_", "")
    return nombre.translate(_CONFUSABLES)


_ARTICULOS = ("el", "la", "los", "las", "the")


def _es_generica(marca: str, comunes: set[str]) -> bool:
    """Nombres formados por palabras comunes ("semana", "elmundo", "lanacion")."""
    if marca in comunes:
        return True
    for articulo in _ARTICULOS:
        if marca.startswith(articulo) and len(marca) > len(articulo) + 2:
            return True
    return False


def detectar_imitacion(host: str, listas_: Listas | None = None) -> dict | None:
    """Devuelve ``{"imita": dominio, "nombre": ..., "motivo": ...}`` si parece imitar a un medio."""
    from rapidfuzz.distance import OSA  # distancia de edición que cuenta un cambio de orden como 1

    listas_ = listas_ or listas()
    cfg = config.valor(config.obtener(), "imitacion", {}) or {}
    host = dominio_de(host)
    if listas_.clasificar(host).categoria is not None:
        return None
    registrado = dominio_registrado(host)
    if registrado in set(cfg.get("excepciones") or []):
        return None
    ext = partes_dominio(host)
    nombre = ext.domain.lower()
    nombre_decodificado = _decodificar(nombre)
    esq = esqueleto(nombre)
    largo_minimo = int(cfg.get("largo_minimo_marca", 5))
    comunes = {texto.normalizar(p) for p in cfg.get("palabras_comunes") or []}
    subdominio = ext.subdomain.lower()

    for marca, dominio_real, nombre_real in listas_.marcas():
        if registrado == dominio_real:
            continue
        # 1. El dominio real aparece como subdominio: clarin.com.noticias-hoy.xyz
        if subdominio and (f"{dominio_real}." in f"{subdominio}." or subdominio == marca):
            return {"imita": dominio_real, "nombre": nombre_real,
                    "motivo": f"usa «{dominio_real}» delante de otro sitio ({registrado})"}
    for marca, dominio_real, nombre_real in listas_.marcas():
        if registrado == dominio_real:
            continue
        esq_marca = esqueleto(marca)
        # 2. Caracteres que imitan a otros (c1arin, clarіn con letra cirílica).
        if esq == esq_marca and nombre != marca:
            detalle = " (usa letras de otros alfabetos)" if nombre_decodificado != nombre else ""
            return {"imita": dominio_real, "nombre": nombre_real,
                    "motivo": f"«{nombre_decodificado}» se ve casi igual que «{marca}»{detalle}"}
        # 3. Mismo nombre con otra terminación: clarin.com.co. No se aplica a nombres
        #    genéricos (elmundo, lanacion), que suelen ser diarios distintos de otro país.
        if nombre == marca and ext.suffix != partes_dominio(dominio_real).suffix and not _es_generica(marca, comunes):
            return {"imita": dominio_real, "nombre": nombre_real,
                    "motivo": f"tiene el mismo nombre que {dominio_real} pero otra terminación (.{ext.suffix})"}
    for marca, dominio_real, nombre_real in listas_.marcas():
        if registrado == dominio_real or len(marca) < largo_minimo or marca in comunes:
            continue
        esq_marca = esqueleto(marca)
        # 4. Diferencia de una o dos letras: clarln, lanacoin
        maximo = int(cfg.get("distancia_maxima_larga", 2)) if len(marca) >= 9 else int(cfg.get("distancia_maxima_corta", 1))
        distancia = OSA.distance(esq, esq_marca)
        if 0 < distancia <= maximo and abs(len(esq) - len(esq_marca)) <= maximo:
            return {"imita": dominio_real, "nombre": nombre_real,
                    "motivo": f"«{nombre}» se diferencia de «{marca}» en {distancia} letra(s)"}
    for marca, dominio_real, nombre_real in listas_.marcas():
        if registrado == dominio_real:
            continue
        # 5. Contiene la marca con palabras agregadas: clarin-noticias.com
        if len(marca) >= max(largo_minimo, 6) and not _es_generica(marca, comunes) and marca in esq and esq != marca:
            return {"imita": dominio_real, "nombre": nombre_real,
                    "motivo": f"contiene el nombre «{marca}» con palabras agregadas"}
    return None


# ----------------------------------------------------------------------
# Antigüedad del dominio
# ----------------------------------------------------------------------

def _fecha_rdap(datos: dict) -> str | None:
    for evento in datos.get("events") or []:
        if str(evento.get("eventAction", "")).lower() in ("registration", "registered"):
            return fecha_iso(evento.get("eventDate"))
    return None


def _whois(dominio: str) -> str | None:
    import whois  # python-whois

    def consultar():
        return whois.whois(dominio)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ejecutor:
        futuro = ejecutor.submit(consultar)
        try:
            datos = futuro.result(timeout=20)
        except concurrent.futures.TimeoutError as e:
            raise red.ErrorRed(red.TIMEOUT, "El servidor WHOIS tardó demasiado.") from e
    creacion = datos.get("creation_date") if hasattr(datos, "get") else getattr(datos, "creation_date", None)
    if isinstance(creacion, list):
        creacion = min((c for c in creacion if isinstance(c, datetime)), default=None)
    return fecha_iso(creacion) if creacion else None


def antiguedad(dominio: str) -> dict:
    """Fecha de creación del dominio, primero por RDAP (HTTPS) y si no por WHOIS."""
    cfg = config.valor(config.obtener(), "fuentes.dominios", {}) or {}
    registrado = dominio_registrado(dominio_de(dominio))
    resultado = {"dominio": registrado, "fecha_creacion": None, "dias": None, "metodo": None,
                 "consulta": None, "error": None, "desde_cache": False}
    if not cfg.get("consultar_antiguedad", True):
        resultado["error"] = "Consulta de antigüedad desactivada en la configuración."
        return resultado
    guardado = cache.obtener("antiguedad", registrado)
    if guardado:
        guardado["desde_cache"] = True
        return _con_dias(guardado)
    url = f"{cfg.get('rdap_url', 'https://rdap.org/domain/')}{registrado}"
    resultado["consulta"] = url
    errores = []
    try:
        respuesta = red.obtener(url, tipo="api")
        resultado["fecha_creacion"] = _fecha_rdap(respuesta.json())
        resultado["metodo"] = "RDAP"
        resultado["consulta"] = respuesta.url
    except (red.ErrorRed, ValueError) as e:
        errores.append(f"RDAP: {getattr(e, 'mensaje', str(e))}")
    if not resultado["fecha_creacion"] and cfg.get("usar_whois_si_falla_rdap", True):
        try:
            fecha = _whois(registrado)
            if fecha:
                resultado["fecha_creacion"] = fecha
                resultado["metodo"] = "WHOIS"
        except Exception as e:  # noqa: BLE001 - WHOIS falla de muchas formas
            errores.append(f"WHOIS: {getattr(e, 'mensaje', type(e).__name__)}")
    if resultado["fecha_creacion"]:
        cache.guardar("antiguedad", registrado, resultado, cache.horas("dominios"))
    else:
        resultado["error"] = (
            "No se pudo obtener la fecha de creación"
            + (f" ({'; '.join(errores)})" if errores else " (el registro no la publica)")
            + ". Algunos países no publican este dato."
        )
    return _con_dias(resultado)


def _con_dias(resultado: dict) -> dict:
    fecha = a_datetime(resultado.get("fecha_creacion"))
    if fecha:
        resultado["dias"] = max(0, (datetime.now(timezone.utc) - fecha).days)
    return resultado
