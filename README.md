# VerificaNoticias

Aplicación para tu computadora que te ayuda a decidir si una noticia es confiable.
Pegas un texto, un titular o un link, y en unos segundos te muestra:

- si **verificadores profesionales** (Chequeado, AFP Factual, Maldita, Newtral, EFE Verifica, Snopes, PolitiFact y otros) ya la analizaron, y qué dijeron;
- **qué otros medios** publican lo mismo, y si son confiables;
- si el **sitio de origen** es conocido, nuevo o una imitación de un medio real;
- **señales de alerta** en el texto: mayúsculas, signos de exclamación, frases de "cadena", falta de autor o de fuentes;
- un **puntaje de 0 a 100** con una etiqueta y la cuenta completa de cómo se calculó, con links a toda la evidencia.

> **Importante:** el resultado es una ayuda para decidir, no una verdad absoluta.
> Mira siempre la evidencia antes de creer o compartir una noticia.

No usa inteligencia artificial: no hay modelos de lenguaje ni locales ni en la nube. Combina fuentes públicas
y reglas transparentes que puedes leer y ajustar. No necesita cuentas, claves ni servicios pagos;
solo conexión a internet.

---

## Índice

1. [Qué necesitas](#1-qué-necesitas)
2. [Instalación paso a paso (Windows)](#2-instalación-paso-a-paso-windows)
3. [Cómo usarla](#3-cómo-usarla)
4. [Cómo leer el resultado](#4-cómo-leer-el-resultado)
5. [De dónde saca la información](#5-de-dónde-saca-la-información)
6. [Cómo se calcula el puntaje](#6-cómo-se-calcula-el-puntaje)
7. [Ajustar pesos y listas de medios](#7-ajustar-pesos-y-listas-de-medios)
8. [Mantener los datos al día](#8-mantener-los-datos-al-día)
9. [Problemas frecuentes](#9-problemas-frecuentes)
10. [Privacidad](#10-privacidad)
11. [Limitaciones conocidas](#11-limitaciones-conocidas)
12. [Para quien quiera mirar el código](#12-para-quien-quiera-mirar-el-código)

---

## 1. Qué necesitas

- Windows 10 u 11.
- Conexión a internet.
- Unos **1,2 GB libres** en el disco: unos 700 MB para el programa y sus librerías, unos 120 MB para la base
  de verificaciones y espacio temporal para descargarla.
- **No** necesitas instalar Python ni nada más: el instalador se encarga de todo.

## 2. Instalación paso a paso (Windows)

1. **Descarga la aplicación.** En la página de GitHub del proyecto, haz clic en el botón verde **Code** y
   luego en **Download ZIP**.
2. **Descomprímela.** Ve a tu carpeta de Descargas, haz clic derecho sobre el archivo `.zip` y elige
   **Extraer todo…** → **Extraer**. Puedes mover la carpeta a donde quieras, por ejemplo a Documentos.
3. **Ejecuta el instalador.** Abre la carpeta y haz doble clic en **`INSTALAR.bat`**.
   - Si aparece un cartel azul que dice **"Windows protegió su PC"**, haz clic en **Más información** y
     después en **Ejecutar de todas formas**. Aparece porque el archivo no está firmado por una empresa.
4. **Espera.** Se abrirá una ventana negra que descarga Python y las librerías dentro de la misma carpeta.
   La primera vez puede tardar entre 5 y 15 minutos, según tu conexión.
5. **Base de verificaciones.** Al final te pregunta si quieres descargar ahora la base de verificaciones
   (unos 200 MB). Presiona **S** para sí o **N** para hacerlo más tarde desde la aplicación.
6. Cuando diga **"Instalación terminada"**, presiona cualquier tecla para cerrar.

Todo queda dentro de la carpeta de la aplicación. **Para desinstalar, basta con borrar la carpeta.**

## 3. Cómo usarla

1. Haz doble clic en **`INICIAR.bat`**.
2. Se abre una ventana negra y, a los pocos segundos, tu navegador con la aplicación
   (la dirección es `http://127.0.0.1:8000`, solo accesible desde tu computadora).
   Si el navegador no se abre solo, copia esa dirección en la barra del navegador.
3. Pega en el cuadro grande el **texto**, el **titular** o el **link** de la noticia.
4. Haz clic en **Analizar** (o presiona Ctrl+Enter). Verás el avance paso a paso; suele tardar entre 15 y 40 segundos.
5. **No cierres la ventana negra** mientras uses la aplicación. Cuando termines, ciérrala para apagarla.

Cada análisis queda guardado en el **Historial** (botón arriba a la derecha), solo en tu computadora.

**Consejo:** si tienes el link de la noticia, úsalo. Así la aplicación puede revisar el sitio de origen,
el autor y la fecha. Si el sitio no deja descargar la nota, la aplicación te avisa y puedes pegar el texto.

## 4. Cómo leer el resultado

Arriba verás un **sello** con la etiqueta y el **puntaje de 0 a 100**:

| Etiqueta | Qué significa |
|---|---|
| **Confirmada** (verde) | 80 puntos o más **y** al menos 3 medios confiables e independientes la publican, o un verificador la calificó como verdadera. |
| **Probablemente verdadera** (verde claro) | De 60 a 79 puntos. Hay señales a favor, pero no alcanzan para darla por confirmada. |
| **Dudosa** (amarillo) | De 40 a 59 puntos, o los verificadores no coinciden entre sí. Señales mixtas: conviene esperar o buscar más. |
| **Probablemente falsa** (naranja) | Menos de 40 puntos. Predominan las alertas y falta respaldo de medios confiables. |
| **Desmentida por verificadores** (rojo) | Un verificador profesional la calificó como **falsa**. Tiene prioridad sobre todo lo demás. |
| **Sin datos suficientes** (gris) | No se encontró información para opinar. **No significa que sea falsa.** |

### "Desmentida" no es lo mismo que "no encontré confirmación"

- **Desmentida** quiere decir que un verificador profesional la revisó y dijo que es falsa. Verás su
  veredicto destacado, con el link a la verificación.
- **No encontrar confirmación** solo resta puntos. Si la noticia afirma algo grave (una muerte, un atentado,
  un decreto) y ningún medio confiable la publica, es una señal de alerta, pero no una prueba.
  **Una noticia de las últimas horas puede no estar publicada todavía**: en ese caso la aplicación resta
  poco y te sugiere volver a analizarla más tarde.

### Debajo del sello

- **Veredicto de verificadores:** las verificaciones encontradas, con el veredicto original, la fecha,
  la afirmación exacta que revisaron y cuánto se parece a tu noticia. **Comprueba que hablen de lo mismo.**
- **Cómo se calculó:** la cuenta completa. Parte de 50 puntos y muestra cada suma y resta, con el total
  acumulado y los links a la evidencia.
- **Quién más la publica:** los artículos de otros medios que dicen algo parecido, marcados como
  *Medio confiable*, *Sin clasificar*, *Poco confiable* o *Humor / sátira*.
- **Fuentes consultadas:** qué fuentes respondieron, cuáles fallaron y por qué. Si una fuente falló,
  eso **no** se cuenta como "nadie la publica".
- **Solo si la noticia resulta confiable**, además verás:
  - una **línea de tiempo** con los artículos ordenados por fecha;
  - un **resumen** armado con frases textuales de esos artículos (no se escribe nada nuevo);
  - el **resumen de Wikipedia** de las personas, lugares u organizaciones mencionadas.

## 5. De dónde saca la información

Todas son fuentes públicas y gratuitas, sin cuenta ni clave:

| Para qué | Fuente |
|---|---|
| ¿Ya fue verificada? | **Feed ClaimReview de Data Commons (Google):** unas 100.000 verificaciones de chequeadores de todo el mundo. Se descarga una vez y se consulta en tu computadora. |
| | **Páginas de los verificadores:** la aplicación busca artículos de verificadores sobre el tema y lee su marcado *ClaimReview*, el formato estándar con que publican el veredicto. Esto es clave para AFP, Snopes, EFE y Chequeado, que casi no aparecen en el feed. |
| ¿Quién más la publica? | **GDELT** (API DOC, últimos 3 meses), **Google News** (RSS de búsqueda) y **DuckDuckGo** (librería `ddgs`). |
| ¿El sitio es confiable? | Tus listas de la carpeta `listas`, más dos listas públicas que se descargan: **domain-quality-ratings** (Lin et al., 2023, *PNAS Nexus*: puntaje de calidad de unos 11.500 dominios) y **OpenSources** (2017, puede estar desactualizada). |
| ¿El dominio es nuevo? | **RDAP** (registro público de dominios, por HTTPS), con **WHOIS** como respaldo. Algunos países no publican la fecha de creación; en ese caso la señal queda neutra. |
| Contexto | **Wikipedia** (API pública), en español y, si no hay artículo, en inglés. |

Para las palabras clave usa **YAKE** y para los nombres propios **spaCy** con modelos pequeños en
español e inglés. Para comparar textos usa **TF-IDF** (scikit-learn) y para el resumen **TextRank**
(librería sumy). Todo funciona en una computadora común.

## 6. Cómo se calcula el puntaje

**Puntaje = 50 + suma de señales**, siempre entre 0 y 100. Los valores son los predeterminados y los
puedes cambiar en `config.yaml` (ver la sección 7).

**Paso 0: veredicto de verificadores (tiene prioridad).** Se busca una verificación cuya afirmación se
parezca a la noticia. Tienen que cumplirse dos condiciones: similitud de texto de 35 % o más, **y** que al
menos el 60 % de sus palabras importantes estén en tu noticia. La segunda condición evita confundir
"las vacunas causan infertilidad" con "las vacunas causan VIH".

| Veredicto | Efecto |
|---|---|
| Falso | Etiqueta *Desmentida por verificadores*; el puntaje no puede superar 10. |
| Engañoso, sacado de contexto, parcialmente falso | Tope de 35. |
| Sin evidencia | Tope de 40. |
| Sátira | Tope de 30. |
| Mayormente verdadero / Verdadero | Mínimo de 70 / 85 (*Confirmada*). |
| Verificadores que se contradicen | *Dudosa*; se muestran todas las verificaciones. |
| Desmentida antes, pero medios confiables la publican **después** | *Dudosa*: puede ser un rumor viejo que ahora sí ocurrió. |

**Señales:**

| Grupo | Señal | Puntos |
|---|---|---|
| Cobertura | Cada medio confiable independiente que dice lo mismo (un grupo editorial cuenta una vez) | +10 (máx. +30) |
| | Cada sitio sin clasificar | +2 (máx. +6) |
| | Cada sitio poco confiable o de humor que la difunde | −3 (máx. −9) |
| | Afirmación de gran impacto que ningún medio confiable publica: más de 48 h / fecha desconocida / menos de 48 h | −20 / −12 / −5 |
| | Ningún medio confiable la publica (afirmación común) | −8 |
| Fuente (si pegas un link) | Medio confiable o verificador | +15 |
| | Sitio poco confiable / de humor | −30 / −20 |
| | Imita a un medio real (c1arin.com, clarin-noticias.com…) | −25 (−10 si el dominio tiene más de 5 años) |
| | Dominio de menos de 6 meses / menos de 2 años / más de 5 años | −15 / −5 / +5 |
| Alertas (máx. −35 en total) | MAYÚSCULAS exageradas · muchos signos de exclamación | −5 cada una |
| | Frases de "cadena" (*urgente*, *compártelo antes de que lo borren*…) | −3 cada una (máx. −12) |
| | Sin autor · sin fecha | −4 cada una |
| | No cita fuentes | −5 |
| | Noticia vieja presentada como nueva | −10 |
| | El titular no coincide con el texto | −8 |
| Calidad (máx. +8) | Cita fuentes · indica autor y fecha | +4 cada una |

## 7. Ajustar pesos y listas de medios

### El archivo `config.yaml`

Se crea en la carpeta de la aplicación la primera vez que la abres. Ábrelo con el **Bloc de notas**
(clic derecho → *Abrir con* → *Bloc de notas*). Cada valor tiene un comentario que explica qué hace.
Por ejemplo, para que cada medio confiable sume 8 en lugar de 10:

```yaml
puntaje:
  corroboracion:
    por_medio_confiable: 8
```

- Respeta los espacios al comienzo de cada línea: indican a qué sección pertenece cada valor.
  Usa espacios, nunca tabulaciones.
- Después de guardar, **cierra la ventana negra y vuelve a abrir `INICIAR.bat`**.
- Si algo se rompe, la aplicación te dice en qué línea está el error. Para volver a los valores
  originales, **borra `config.yaml`** y vuelve a abrir la aplicación.

Además de los pesos, puedes cambiar las palabras de "cadena" que se buscan, las palabras de gran impacto,
los umbrales de cada etiqueta y qué fuentes se consultan.

### Las listas de medios (carpeta `listas`)

Son cuatro archivos que puedes abrir con **Excel** o con el Bloc de notas:

| Archivo | Para qué |
|---|---|
| `medios_confiables.csv` | Medios que suman puntos. La columna `grupo` sirve para que medios del mismo dueño (por ejemplo, Clarín y TN) cuenten como uno solo. |
| `verificadores.csv` | Verificadores de datos. Se puede indicar una sección, por ejemplo `reuters.com/fact-check`. |
| `desinformacion.csv` | Sitios poco confiables. La columna `motivo` se muestra en el resultado: escribe por qué está en la lista. |
| `satira.csv` | Sitios de humor que publican noticias inventadas a propósito. |

Para agregar un medio, agrega una fila. Basta con la columna `dominio`, por ejemplo `eldiario.com.ar`;
las demás son opcionales. Si usas Excel, guarda con **Archivo → Guardar como → CSV UTF-8**.
La aplicación también entiende los CSV con punto y coma que genera Excel en español.

**Tus listas siempre tienen prioridad sobre las listas públicas importadas.** Si una lista pública marca
mal un sitio, agrégalo en la lista correcta y listo.

## 8. Mantener los datos al día

El botón **Actualizar datos**, al pie de la aplicación, descarga de nuevo:

- la base de verificaciones (unos 200 MB; se actualiza a diario en origen);
- las listas públicas de dominios.

Conviene hacerlo **una vez por semana**: la aplicación te avisa cuando la base tiene más de 7 días.
También puedes usar **`ACTUALIZAR_DATOS.bat`** sin abrir la aplicación.

Las búsquedas se guardan en una **caché local** durante unas horas (6 h las búsquedas, 7 días los
artículos), así que analizar dos veces lo mismo es más rápido y no repite consultas.

## 9. Problemas frecuentes

| Problema | Qué hacer |
|---|---|
| **"No hay conexión a internet"** | Revisa tu conexión. Sin internet solo se analizan el texto y las listas locales, y el resultado lo indica. |
| **"Se alcanzó el límite de consultas"** (DuckDuckGo o GDELT) | Pasa cuando haces muchos análisis seguidos. Espera unos minutos. Las demás fuentes siguen funcionando. |
| **"El sitio bloqueó la descarga"** o **"no se pudo extraer el texto"** | Algunos medios bloquean descargas automáticas o tienen muro de pago. Copia el texto de la noticia y pégalo. |
| **Una fuente "tardó demasiado"** | El sitio está lento o caído. El análisis sigue con las demás fuentes; vuelve a intentarlo más tarde. |
| **Errores de certificado** o todas las fuentes fallan aunque tengas internet | Algunos antivirus inspeccionan las conexiones. La aplicación usa los certificados de Windows para evitarlo; si sigue pasando, prueba pausar la protección web del antivirus. |
| **El navegador no se abre solo** | Copia la dirección que muestra la ventana negra (`http://127.0.0.1:8000`) en tu navegador. |
| **"La aplicación todavía no está instalada"** | Ejecuta primero `INSTALAR.bat`. |
| **La instalación falló a mitad de camino** | Vuelve a ejecutar `INSTALAR.bat`: retoma lo que falta. |
| **Otro error inesperado** | El detalle queda en `datos\errores.log`. |

## 10. Privacidad

- El historial, la caché y tu configuración quedan **solo en tu computadora**, en la carpeta `datos`.
- La aplicación solo es accesible desde tu computadora (`127.0.0.1`); nadie más en tu red puede usarla.
- Para buscar, envía **palabras clave de la noticia** a GDELT, Google News, DuckDuckGo y Wikipedia;
  el **nombre del dominio** a RDAP/WHOIS; y, si pegas un link, descarga esa página del sitio. Nada más.
- No hay cuentas, ni publicidad, ni estadísticas de uso.

## 11. Limitaciones conocidas

- **Es una ayuda, no un juez.** Las reglas son simples y pueden equivocarse: siempre mira la evidencia.
- **La comparación de textos no entiende el sentido.** Mide palabras en común: "X murió" y "es falso que
  X murió" se parecen mucho. Por eso los artículos cuyo titular dice que algo es falso se separan, y
  siempre se muestra qué afirmación revisó cada verificador.
- **No cruza idiomas.** Una verificación en inglés no coincide con una noticia en español. Se analizan
  noticias en español y en inglés, cada una con fuentes de su idioma.
- **Cobertura del feed ClaimReview.** Tiene muchas verificaciones de Newtral, Maldita, Fast Check,
  Univision, PolitiFact y FactCheck.org, pero casi ninguna de AFP, Snopes, EFE o Chequeado. Para esos se
  buscan sus páginas en vivo, lo que depende de los buscadores.
- **GDELT solo cubre los últimos 3 meses.** Para noticias más viejas se usan Google News y DuckDuckGo.
- **Las listas públicas de desinformación son sobre todo de EE. UU.** La lista en español empieza chica,
  con casos bien documentados; puedes ampliarla con sitios que conozcas.
- **Los buscadores gratuitos pueden limitar** las consultas si se usan mucho seguido.

## 12. Para quien quiera mirar el código

Está escrito en Python, sin servicios externos de IA. La estructura:

```
verificanoticias/
  pipeline.py            orquesta el análisis paso a paso
  extraccion.py          lee texto o URL (trafilatura)
  nlp.py                 palabras clave (YAKE) y nombres propios (spaCy)
  similitud.py           TF-IDF y cobertura de palabras
  senales.py             señales de alerta del texto
  puntaje.py             fórmula y desglose
  resumen.py             línea de tiempo y TextRank (sumy)
  dominios.py            listas, imitaciones, antigüedad (RDAP/WHOIS)
  fuentes/               GDELT, Google News, DuckDuckGo, ClaimReview, Wikipedia
  actualizar.py          descarga de listas públicas y del feed ClaimReview
  cache.py, historial.py SQLite local
  web/                   servidor FastAPI e interfaz (HTML + JS sin dependencias)
  config_predeterminada.yaml
listas/                  listas editables de medios
tests/                   tests automáticos (sin conexión a internet)
```

En otro sistema (Linux o macOS), con [uv](https://docs.astral.sh/uv/) instalado:

```bash
uv sync                                    # instala todo
uv run python -m verificanoticias          # abre la aplicación
uv run python -m verificanoticias.actualizar   # actualiza datos
uv run pytest                              # corre los tests
```

### Créditos de los datos

- Feed ClaimReview: [Data Commons](https://datacommons.org) y los verificadores que publican
  con el estándar [ClaimReview](https://schema.org/ClaimReview).
- [domain-quality-ratings](https://github.com/hauselin/domain-quality-ratings): Lin, H., Lasser, J.,
  Lewandowsky, S., Cole, R., Gully, A., Rand, D. G. y Pennycook, G. (2023). *High level of correspondence
  across different news domain quality rating sets.* PNAS Nexus, 2(9).
- [OpenSources](https://github.com/BigMcLargeHuge/opensources) (2017).
- [GDELT Project](https://www.gdeltproject.org/), Google News, DuckDuckGo y Wikipedia.
