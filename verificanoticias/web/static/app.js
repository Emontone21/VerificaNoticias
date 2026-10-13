/* VerificaNoticias - interfaz (JavaScript sin dependencias) */
"use strict";

const $ = (sel) => document.querySelector(sel);

const NOMBRES_CATEGORIA = {
  confiable: "Medio confiable",
  verificador: "Verificador",
  desinformacion: "Poco confiable",
  satira: "Humor / sátira",
};
const ESTADOS_FUENTE = {
  ok: "Respondió",
  sin_resultados: "Sin resultados",
  error: "Falló",
  omitida: "No consultada",
  desactivada: "Desactivada",
};
const ICONOS_PASO = { pendiente: "○", en_curso: "", listo: "✓", omitido: "–" };

let estadoApp = { umbrales: { dudosa: 40, probablemente_verdadera: 60, confirmada: 80 }, base: 50 };
let consultaActual = null;

/* ------------------------------------------------------------------ */
/* Utilidades                                                          */
/* ------------------------------------------------------------------ */

function esc(valor) {
  return String(valor ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function urlSegura(url) {
  return typeof url === "string" && /^https?:\/\//i.test(url) ? url : null;
}

function enlace(url, texto) {
  const segura = urlSegura(url);
  if (!segura) return esc(texto || url || "");
  return `<a href="${esc(segura)}" target="_blank" rel="noopener noreferrer">${esc(texto || segura)}</a>`;
}

function fecha(iso, conHora = false) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const opciones = { day: "2-digit", month: "2-digit", year: "numeric" };
  if (conHora) Object.assign(opciones, { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleString("es", opciones);
}

function porcentaje(valor) {
  return `${Math.round((valor || 0) * 100)}%`;
}

function numero(n) {
  return Number(n || 0).toLocaleString("es");
}

function puntos(p) {
  const v = Math.round(p || 0);
  if (v > 0) return `<span class="suma">+${v}</span>`;
  if (v < 0) return `<span class="resta">−${Math.abs(v)}</span>`;
  return `<span class="nada">·</span>`;
}

async function api(ruta, opciones = {}) {
  let respuesta;
  try {
    respuesta = await fetch(ruta, {
      headers: { "Content-Type": "application/json" },
      ...opciones,
    });
  } catch (e) {
    throw new Error("Se perdió la conexión con la aplicación. ¿Cerraste la ventana negra? Vuelve a abrirla con INICIAR.bat.");
  }
  let datos = null;
  try {
    datos = await respuesta.json();
  } catch (e) {
    datos = null;
  }
  if (!respuesta.ok) {
    const detalle = datos && datos.detail ? datos.detail : `Error ${respuesta.status}`;
    throw new Error(typeof detalle === "string" ? detalle : "La aplicación rechazó el pedido.");
  }
  return datos;
}

/* ------------------------------------------------------------------ */
/* Análisis                                                            */
/* ------------------------------------------------------------------ */

function mostrarError(mensaje) {
  const el = $("#error-entrada");
  el.textContent = mensaje;
  el.hidden = !mensaje;
}

function pintarProgreso(datos) {
  const pasos = datos.pasos || [];
  $("#pasos").innerHTML = pasos
    .map(
      (p) => `<li class="paso ${esc(p.estado)}">
        <span class="paso-icono" aria-hidden="true">${ICONOS_PASO[p.estado] ?? ""}</span>
        <span>${esc(p.nombre)}${p.detalle ? `<span class="paso-detalle">${esc(p.detalle)}</span>` : ""}</span>
      </li>`
    )
    .join("");
  const valor = datos.porcentaje || 0;
  $("#barra-relleno").style.width = `${valor}%`;
  $("#barra-progreso").setAttribute("aria-valuenow", String(valor));
}

async function analizar(evento) {
  evento.preventDefault();
  const texto = $("#texto").value.trim();
  mostrarError("");
  if (!texto) {
    mostrarError("Pega el texto, el titular o el link de la noticia.");
    $("#texto").focus();
    return;
  }
  const boton = $("#btn-analizar");
  boton.disabled = true;
  boton.textContent = "Analizando…";
  $("#resultado").hidden = true;
  $("#progreso").hidden = false;
  pintarProgreso({ pasos: [], porcentaje: 3 });
  try {
    const { id } = await api("/api/analizar", { method: "POST", body: JSON.stringify({ texto }) });
    consultaActual = id;
    await seguir(id);
  } catch (e) {
    mostrarError(e.message);
    $("#progreso").hidden = true;
  } finally {
    boton.disabled = false;
    boton.textContent = "Analizar";
  }
}

async function seguir(id) {
  while (consultaActual === id) {
    const datos = await api(`/api/trabajos/${encodeURIComponent(id)}`);
    pintarProgreso(datos);
    if (datos.estado === "listo") {
      $("#progreso").hidden = true;
      mostrarResultado(datos.resultado, true);
      cargarHistorial();
      return;
    }
    if (datos.estado === "error") {
      $("#progreso").hidden = true;
      mostrarError(datos.error);
      return;
    }
    await new Promise((r) => setTimeout(r, 700));
  }
}

/* ------------------------------------------------------------------ */
/* Resultado                                                           */
/* ------------------------------------------------------------------ */

function medidor(valor) {
  const u = estadoApp.umbrales;
  const franjas = [
    [0, u.dudosa, "--c-probablemente_falsa"],
    [u.dudosa, u.probablemente_verdadera, "--c-dudosa"],
    [u.probablemente_verdadera, u.confirmada, "--c-probablemente_verdadera"],
    [u.confirmada, 100, "--c-confirmada"],
  ];
  const tramos = franjas
    .map(([a, b, c]) => `<div class="medidor-franja" style="width:${b - a}%;background:color-mix(in srgb, var(${c}) 55%, var(--hoja))"></div>`)
    .join("");
  const escala = [0, u.dudosa, u.probablemente_verdadera, u.confirmada, 100]
    .map((n) => `<span style="left:${n}%">${n}</span>`)
    .join("");
  return `<div class="medidor" aria-hidden="true">
      <div class="medidor-franjas">${tramos}</div>
      <div class="medidor-marca" style="left:${Math.max(0, Math.min(100, valor))}%"></div>
      <div class="medidor-escala">${escala}</div>
    </div>`;
}

function tarjetaVeredicto(r, animar) {
  const res = r.resultado;
  const titulo = r.noticia && r.noticia.titulo ? r.noticia.titulo : r.entrada;
  return `<section class="tarjeta veredicto" data-etiqueta="${esc(res.clave_etiqueta)}" aria-labelledby="etiqueta-resultado">
    <div>
      <p class="veredicto-titulo">${esc(titulo.length > 160 ? titulo.slice(0, 160) + "…" : titulo)}</p>
      <div id="etiqueta-resultado" class="sello${animar ? " animar" : ""}">${esc(res.etiqueta)}</div>
      <p class="veredicto-explicacion">${esc(res.explicacion)}</p>
    </div>
    <div class="puntaje">
      <div class="puntaje-numero" aria-label="Puntaje de credibilidad: ${res.puntaje} de 100">${res.puntaje}<small>/100</small></div>
      <div class="puntaje-rotulo">Puntaje de credibilidad · ${res.medios_confiables_independientes} medio(s) confiable(s)</div>
      ${medidor(res.puntaje)}
    </div>
  </section>`;
}

function bloqueAvisos(r) {
  const avisos = r.advertencias || [];
  if (!avisos.length) return "";
  return `<ul class="avisos">${avisos.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>`;
}

function itemVerificacion(v) {
  const compartidas = (v.palabras_compartidas || []).length
    ? ` · palabras en común: ${esc(v.palabras_compartidas.join(", "))}` : "";
  return `<div class="verificacion">
    <div class="verificacion-cabecera">
      <span class="mini-sello" data-cat="${esc(v.categoria)}">${esc(v.veredicto || v.categoria_nombre)}</span>
      <strong>${esc(v.organizacion || v.dominio || "Verificador")}</strong>
      <span class="meta">${v.fecha ? esc(fecha(v.fecha)) + " · " : ""}${esc(v.categoria_nombre)}</span>
    </div>
    ${v.afirmacion ? `<p class="afirmacion">${esc(v.afirmacion)}</p>` : ""}
    ${v.explicacion ? `<p class="meta">${esc(v.explicacion)}</p>` : ""}
    <p class="meta">${enlace(v.url, "Leer la verificación")} · similitud con tu noticia: ${porcentaje(v.similitud)}
      · palabras clave presentes: ${porcentaje(v.cobertura_palabras)}${compartidas} · fuente: ${esc(v.origen || "")}</p>
  </div>`;
}

function bloqueVerificadores(r) {
  const ver = r.verificaciones || {};
  const fuertes = ver.fuertes || [];
  const relacionadas = ver.relacionadas || [];
  const sinMarcado = ver.sin_marcado || [];
  if (!fuertes.length && !relacionadas.length && !sinMarcado.length) return "";
  const positivo = fuertes.length && fuertes.every((v) => ["verdadero", "mayormente_verdadero"].includes(v.categoria));
  const clase = !fuertes.length ? "neutro" : positivo ? "positivo" : "";
  let html = `<section class="tarjeta verificadores ${clase}"><h2>Veredicto de verificadores</h2>`;
  if (fuertes.length) {
    html += `<p class="tarjeta-sub">Verificadores profesionales ya analizaron esta afirmación. Su veredicto tiene prioridad sobre las demás señales. Comprueba que hablen de lo mismo que tu noticia.</p>`;
    html += fuertes.map(itemVerificacion).join("");
  } else {
    html += `<p class="tarjeta-sub">No se encontró una verificación de esta afirmación exacta.</p>`;
  }
  if (relacionadas.length) {
    html += `<details><summary>Verificaciones de afirmaciones parecidas (${relacionadas.length}) — no se aplicaron al puntaje</summary>
      ${relacionadas.map(itemVerificacion).join("")}</details>`;
  }
  if (sinMarcado.length) {
    html += `<details${!fuertes.length ? " open" : ""}><summary>Artículos de verificadores sobre el tema (${sinMarcado.length})</summary>
      <ul class="articulos">${sinMarcado
        .map(
          (a) => `<li class="articulo">${enlace(a.url, a.titulo || a.url)}
          <span class="meta">${esc(a.dominio || "")}${a.veredicto_titulo ? ` · el título indica: <strong>${esc(a.veredicto_titulo === "falso" ? "falso" : "engañoso")}</strong>` : ""}${a.error ? ` · no se pudo leer: ${esc(a.error)}` : ""}</span></li>`
        )
        .join("")}</ul></details>`;
  }
  return html + `</section>`;
}

function bloqueCuentas(r) {
  const res = r.resultado;
  let acumulado = res.base;
  let grupoActual = null;
  let filas = `<tr class="inicio"><td>Punto de partida (neutral)</td><td class="num"></td><td class="num">${acumulado}</td></tr>`;
  for (const s of res.senales) {
    if (s.grupo !== grupoActual) {
      grupoActual = s.grupo;
      filas += `<tr class="grupo"><td colspan="3">${esc(s.nombre_grupo)}</td></tr>`;
    }
    acumulado += Math.round(s.puntos || 0);
    const evidencias = (s.evidencias || []).length
      ? `<ul class="senal-evidencia">${s.evidencias
          .map((e) => `<li>${enlace(e.url, e.titulo)}${e.medio ? ` <span class="meta">— ${esc(e.medio)}${e.fecha ? ", " + esc(fecha(e.fecha)) : ""}</span>` : ""}</li>`)
          .join("")}</ul>`
      : "";
    filas += `<tr class="${s.informativa ? "informativa" : ""}">
      <td><span class="senal-titulo">${esc(s.titulo)}</span><span class="senal-detalle">${esc(s.detalle)}</span>${evidencias}</td>
      <td class="num">${puntos(s.puntos)}</td>
      <td class="num acumulado">${Math.round(acumulado)}</td></tr>`;
  }
  filas += `<tr class="total"><td>Puntaje final</td><td class="num"></td><td class="num">${res.puntaje}</td></tr>`;
  return `<section class="tarjeta"><h2>Cómo se calculó</h2>
    <p class="tarjeta-sub">Se parte de ${res.base} puntos. Cada señal suma o resta según los pesos de <code>config.yaml</code>. Las filas con «·» son informativas.</p>
    <table class="cuentas"><thead><tr><th>Señal</th><th class="num">Puntos</th><th class="num">Total</th></tr></thead>
    <tbody>${filas}</tbody></table></section>`;
}

function bloqueFuentes(r) {
  const items = (r.fuentes_consultadas || [])
    .map((f) => {
      const consultas = (f.consultas || []).filter(urlSegura).slice(0, 3);
      const links = consultas.length
        ? `${f.mensaje ? "<br>" : ""}${consultas.map((u, i) => enlace(u, consultas.length > 1 ? `consulta ${i + 1}` : "ver consulta")).join(" · ")}`
        : "";
      const extra = [];
      if (f.cantidad) extra.push(`${f.cantidad} resultado(s)`);
      if (f.desde_cache) extra.push("desde caché");
      return `<li class="fuente-item">
        <span class="estado ${esc(f.estado)}">${esc(ESTADOS_FUENTE[f.estado] || f.estado)}</span>
        <span class="fuente-nombre">${esc(f.nombre)}${extra.length ? ` <span class="meta">(${esc(extra.join(", "))})</span>` : ""}</span>
        <span class="fuente-mensaje">${esc(f.mensaje || "")}${links}</span></li>`;
    })
    .join("");
  return `<section class="tarjeta"><h2>Fuentes consultadas</h2>
    <p class="tarjeta-sub">Solo se muestran links que la aplicación consultó de verdad.</p>
    <ul class="fuentes">${items}</ul></section>`;
}

function insignia(categoria) {
  return categoria
    ? `<span class="insignia ${esc(categoria)}">${esc(NOMBRES_CATEGORIA[categoria] || categoria)}</span>`
    : `<span class="insignia ninguna">Sin clasificar</span>`;
}

function itemArticulo(a) {
  return `<li class="articulo">
    <span>${insignia(a.categoria)} <strong>${esc(a.medio || a.dominio)}</strong></span>
    ${enlace(a.url, a.titulo || a.url)}
    <span class="meta">${a.fecha ? esc(fecha(a.fecha)) + " · " : ""}similitud ${porcentaje(a.similitud)} · encontrado en ${esc(a.fuente_busqueda || "")}</span>
  </li>`;
}

function bloqueCobertura(r) {
  const cob = r.cobertura || {};
  const coincidencias = cob.coincidencias || [];
  const relacionados = cob.relacionados || [];
  let html = `<section class="tarjeta"><h2>Quién más la publica</h2>
    <p class="tarjeta-sub">Artículos que dicen algo parecido (similitud de texto de ${porcentaje(cob.umbral)} o más).</p>`;
  if (coincidencias.length) {
    html += `<ul class="articulos">${coincidencias.map(itemArticulo).join("")}</ul>`;
  } else if ((cob.fuentes_consultadas || []).length) {
    html += `<p class="vacio">Ningún artículo encontrado dice algo suficientemente parecido. Si la noticia es de las últimas horas, vuelve a analizarla más tarde.</p>`;
  } else {
    html += `<p class="vacio">No se pudo buscar en otros medios (revisa «Fuentes consultadas»).</p>`;
  }
  const desmentidas = cob.desmentidas_en_medios || [];
  if (desmentidas.length) {
    html += `<details open><summary>Artículos que la desmienten o la ponen en duda (${desmentidas.length})</summary>
      <ul class="articulos">${desmentidas.map(itemArticulo).join("")}</ul></details>`;
  }
  if (relacionados.length) {
    html += `<details><summary>Otros resultados del mismo tema que no coinciden lo suficiente (${relacionados.length})</summary>
      <ul class="articulos">${relacionados.map(itemArticulo).join("")}</ul></details>`;
  }
  return html + `</section>`;
}

function bloqueNoticia(r) {
  const n = r.noticia || {};
  const f = r.fuente || {};
  const filas = [];
  if (n.tipo === "url") {
    filas.push(["Dirección", enlace(n.url, n.url)]);
    filas.push(["Sitio", `${esc(n.dominio)} ${insignia(f.categoria)}${f.origen ? ` <span class="meta">según ${esc(f.origen)}</span>` : ""}`]);
    if (f.imitacion) filas.push(["Atención", `<strong>Parece imitar a ${esc(f.imitacion.imita)}</strong>: ${esc(f.imitacion.motivo)}`]);
    const ant = f.antiguedad || {};
    filas.push(["Dominio creado", ant.fecha_creacion ? `${esc(fecha(ant.fecha_creacion))} (${numero(ant.dias)} días)` : `<span class="meta">${esc(ant.error || "desconocido")}</span>`]);
    filas.push(["Autor", n.autor ? esc(n.autor) : `<span class="meta">no figura</span>`]);
    filas.push(["Fecha", n.fecha ? esc(fecha(n.fecha)) : `<span class="meta">no figura</span>`]);
  } else {
    filas.push(["Tipo", "Texto pegado (sin link a la fuente original)"]);
  }
  filas.push(["Idioma detectado", n.idioma === "en" ? "inglés" : "español"]);
  const consultas = r.consultas || {};
  if (consultas.consulta) filas.push(["Búsqueda usada", `<code>${esc(consultas.consulta)}</code>`]);
  if ((consultas.entidades || []).length) {
    filas.push(["Nombres detectados", esc(consultas.entidades.map((e) => `${e.texto} (${e.tipo})`).join(", "))]);
  }
  const extracto = n.cuerpo_extracto ? `<p class="extracto">${esc(n.cuerpo_extracto)}</p>` : "";
  return `<section class="tarjeta"><h2>La noticia analizada</h2>
    <dl class="ficha">${filas.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>${extracto}</section>`;
}

function bloqueContexto(r) {
  const c = r.contexto;
  if (!c) return "";
  let html = "";
  if ((c.linea_de_tiempo || []).length) {
    html += `<section class="tarjeta"><h2>Línea de tiempo</h2>
      <p class="tarjeta-sub">Cómo la fueron publicando distintos medios, del más antiguo al más reciente.</p>
      <ol class="linea-tiempo">${c.linea_de_tiempo
        .map((a) => `<li><time${a.fecha ? ` datetime="${esc(a.fecha)}"` : ""}>${a.fecha ? esc(fecha(a.fecha, true)) : "sin fecha"}</time>
          ${insignia(a.categoria)} <strong>${esc(a.medio || a.dominio)}</strong><br>${enlace(a.url, a.titulo || a.url)}</li>`)
        .join("")}</ol></section>`;
  }
  if ((c.resumen || []).length) {
    html += `<section class="tarjeta"><h2>Resumen</h2>
      <p class="tarjeta-sub">Frases elegidas automáticamente (TextRank) de los artículos. No se escribió nada nuevo: cada frase es textual.</p>
      <ul class="resumen-frases">${c.resumen
        .map((f) => `<li><q>${esc(f.frase)}</q><span class="meta">— ${f.url ? enlace(f.url, f.medio || f.url) : esc(f.medio || "texto analizado")}</span></li>`)
        .join("")}</ul></section>`;
  }
  if ((c.wikipedia || []).length) {
    html += `<section class="tarjeta"><h2>Contexto en Wikipedia</h2>
      <p class="tarjeta-sub">Personas, lugares y organizaciones mencionadas.</p>
      <div class="wiki">${c.wikipedia
        .map((w) => `<article><h3>${enlace(w.url, w.titulo)}</h3>${w.descripcion ? `<p class="meta">${esc(w.descripcion)}</p>` : ""}<p>${esc(w.extracto.length > 420 ? w.extracto.slice(0, 420) + "…" : w.extracto)}</p></article>`)
        .join("")}</div></section>`;
  }
  return html;
}

function mostrarResultado(r, animar = false) {
  const el = $("#resultado");
  el.innerHTML = `
    ${tarjetaVeredicto(r, animar)}
    ${bloqueAvisos(r)}
    ${bloqueVerificadores(r)}
    ${bloqueCuentas(r)}
    <div class="dos-columnas">${bloqueCobertura(r)}${bloqueFuentes(r)}</div>
    ${bloqueContexto(r)}
    ${bloqueNoticia(r)}
    <p class="meta">Analizado el ${esc(fecha(r.fecha_analisis, true))} en ${esc(r.duracion_segundos)} segundos.
    Recuerda: el resultado es una ayuda para decidir, no una verdad absoluta.</p>`;
  el.hidden = false;
  el.focus({ preventScroll: true });
  el.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}

/* ------------------------------------------------------------------ */
/* Historial                                                           */
/* ------------------------------------------------------------------ */

async function cargarHistorial() {
  let items = [];
  try {
    items = await api("/api/historial");
  } catch (e) {
    $("#lista-historial").innerHTML = `<li class="vacio">${esc(e.message)}</li>`;
    return;
  }
  $("#historial-cantidad").textContent = items.length ? String(items.length) : "";
  $("#btn-borrar-historial").hidden = !items.length;
  if (!items.length) {
    $("#lista-historial").innerHTML = `<li class="vacio">Todavía no analizaste ninguna noticia. Los análisis aparecerán aquí.</li>`;
    return;
  }
  $("#lista-historial").innerHTML = items
    .map(
      (h) => `<li class="item-historial" data-etiqueta="${esc(h.clave_etiqueta)}">
        <button type="button" class="abrir" data-id="${h.id}">
          <span class="h-titulo">${esc(h.titulo || h.entrada)}</span>
          <span class="h-meta">${esc(h.etiqueta)} · ${esc(h.puntaje)}/100 · ${esc(fecha(h.fecha, true))}</span>
        </button>
        <button type="button" class="boton-icono borrar" data-id="${h.id}" aria-label="Borrar este análisis">×</button>
      </li>`
    )
    .join("");
}

async function abrirDelHistorial(id) {
  try {
    const r = await api(`/api/historial/${encodeURIComponent(id)}`);
    consultaActual = null;
    $("#progreso").hidden = true;
    mostrarError("");
    alternarHistorial(false);
    mostrarResultado(r, false);
  } catch (e) {
    alert(e.message);
  }
}

function alternarHistorial(abrir) {
  const panel = $("#panel-historial");
  const mostrar = abrir ?? panel.hidden;
  panel.hidden = !mostrar;
  $("#btn-historial").setAttribute("aria-expanded", String(mostrar));
  if (mostrar) {
    cargarHistorial();
    $("#btn-cerrar-historial").focus();
  }
}

/* ------------------------------------------------------------------ */
/* Estado de los datos y actualización                                 */
/* ------------------------------------------------------------------ */

async function cargarEstado() {
  try {
    const e = await api("/api/estado");
    estadoApp = e;
    const indice = e.indice || {};
    const listas = e.listas || {};
    const base = indice.disponible
      ? `Base de verificaciones: <strong>${numero(indice.cantidad)}</strong> (actualizada el ${esc(fecha(indice.fecha_actualizacion))})${indice.desactualizado ? " — conviene actualizarla" : ""}`
      : `<strong>La base de verificaciones no está descargada.</strong> Pulsa «Actualizar datos» (unos 200 MB, una sola vez).`;
    const misListas = ["medios_confiables.csv", "verificadores.csv", "desinformacion.csv", "satira.csv"]
      .reduce((t, k) => t + (listas[k] || 0), 0);
    $("#estado-datos").innerHTML = `${base}<br>Listas: ${numero(misListas)} dominios en tus listas, ${numero(listas.importadas || 0)} importados.`;
    if (e.actualizacion && e.actualizacion.estado === "en_curso") seguirActualizacion();
  } catch (err) {
    $("#estado-datos").textContent = err.message;
  }
}

async function actualizarDatos() {
  const boton = $("#btn-actualizar");
  boton.disabled = true;
  $("#mensaje-actualizacion").textContent = "Comenzando…";
  try {
    await api("/api/actualizar", { method: "POST", body: JSON.stringify({ incluir_feed: true }) });
    await seguirActualizacion();
  } catch (e) {
    $("#mensaje-actualizacion").textContent = e.message;
    boton.disabled = false;
  }
}

async function seguirActualizacion() {
  const boton = $("#btn-actualizar");
  boton.disabled = true;
  for (;;) {
    let estado;
    try {
      estado = await api("/api/actualizacion");
    } catch (e) {
      $("#mensaje-actualizacion").textContent = e.message;
      break;
    }
    $("#mensaje-actualizacion").textContent = estado.mensaje || "";
    if (estado.estado !== "en_curso") {
      if (estado.estado === "lista") $("#mensaje-actualizacion").textContent = "Datos actualizados.";
      await cargarEstado();
      break;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  boton.disabled = false;
}

/* ------------------------------------------------------------------ */
/* Inicio                                                              */
/* ------------------------------------------------------------------ */

document.addEventListener("DOMContentLoaded", () => {
  $("#form-analisis").addEventListener("submit", analizar);
  $("#texto").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("#form-analisis").requestSubmit();
  });
  $("#btn-historial").addEventListener("click", () => alternarHistorial());
  $("#btn-cerrar-historial").addEventListener("click", () => alternarHistorial(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("#panel-historial").hidden) alternarHistorial(false);
  });
  $("#lista-historial").addEventListener("click", async (e) => {
    const abrir = e.target.closest("button.abrir");
    const borrar = e.target.closest("button.borrar");
    if (abrir) abrirDelHistorial(abrir.dataset.id);
    if (borrar) {
      await api(`/api/historial/${encodeURIComponent(borrar.dataset.id)}`, { method: "DELETE" });
      cargarHistorial();
    }
  });
  $("#btn-borrar-historial").addEventListener("click", async () => {
    if (confirm("¿Borrar todo el historial? No se puede deshacer.")) {
      await api("/api/historial", { method: "DELETE" });
      cargarHistorial();
    }
  });
  $("#btn-actualizar").addEventListener("click", actualizarDatos);
  cargarEstado();
  cargarHistorial();
});
