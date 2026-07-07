// Claude / AI Documentation page — prompts, workflow, interactive playground
function ClaudeDocsPage() {
  const toast = useToast();
  const [copied, setCopied] = React.useState(null);
  const [prompt, setPrompt] = React.useState(
    "Sos asistente de OptiFull. ¿Qué métricas debería incluir en el reporte semanal de tienda?"
  );
  const [response, setResponse] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [contextOn, setContextOn] = React.useState(true);

  const copy = async (txt, id) => {
    try {
      await navigator.clipboard.writeText(txt);
      setCopied(id);
      setTimeout(() => setCopied(null), 1800);
      toast("Copiado al portapapeles", { kind: "success" });
    } catch (e) {
      toast("No se pudo copiar", { kind: "warn" });
    }
  };

  const ask = async () => {
    if (!prompt.trim() || loading) return;
    setLoading(true); setResponse("");
    try {
      const ctx = contextOn ? PROJECT_CONTEXT + "\n\n" : "";
      const text = await window.claude.complete(ctx + prompt);
      setResponse(text);
    } catch (e) {
      setResponse("⚠ Error al llamar al asistente. Intentá de nuevo.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="content docs">
      <div className="page-head">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <span className="claude-badge"><IcoSparkle size={12} stroke={2} /> ASISTENTE IA</span>
            <span style={{ fontSize: 11, color: "var(--fg-3)" }} className="mono">claude-haiku-4-5 · v0.3</span>
          </div>
          <h1>Asistente IA & Claude Design</h1>
          <p>Cómo se usa la IA en el desarrollo de OptiFull — prompts, patrones y playground interactivo.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-sec" onClick={() => copy(PROJECT_CONTEXT, "ctx-full")}>
            <IcoCopy style={{ marginRight: 6 }} />{copied === "ctx-full" ? "Copiado!" : "Copiar contexto completo"}
          </button>
        </div>
      </div>

      {/* Quick nav */}
      <div className="docs-nav">
        <a href="#workflow">Workflow</a>
        <a href="#prompts">Prompts</a>
        <a href="#playground">Playground</a>
        <a href="#guidelines">Guidelines</a>
        <a href="#context">Contexto</a>
      </div>

      {/* ── WORKFLOW ────────────────────────────────────────── */}
      <section id="workflow" className="docs-section">
        <div className="docs-sec-head">
          <h2><span className="docs-sec-num">01</span>Workflow con IA</h2>
          <p>Cómo se integra Claude en el ciclo de desarrollo del proyecto.</p>
        </div>

        <div className="workflow-steps">
          {[
            { n: 1, t: "Contexto", d: "Adjuntar OptiFull_Contexto_para_IA.pdf al inicio de cada conversación. Asegura que el asistente tenga: dominio, stack, alcance y estado actual."},
            { n: 2, t: "Pedido específico", d: "Definir verbo de acción (escribir / implementar / diseñar / revisar), formato esperado (tabla / código / texto) y restricciones (longitud, idioma, estilo)."},
            { n: 3, t: "Iteración", d: "Refinar con prompts de seguimiento. Citar la respuesta anterior y pedir ajustes puntuales en lugar de rehacer todo."},
            { n: 4, t: "Validación", d: "Validar contra el documento de contexto. Si Claude se desvía del alcance (ej: propone reconocimiento facial), corregir el prompt."},
            { n: 5, t: "Integración", d: "Copiar el output a su lugar (código → repo, redacción → informe). Marcar la versión y commit message si aplica."},
          ].map(s => (
            <div key={s.n} className="wf-step">
              <div className="wf-num mono">{s.n.toString().padStart(2, "0")}</div>
              <div>
                <div className="wf-title">{s.t}</div>
                <div className="wf-desc">{s.d}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── PROMPTS ─────────────────────────────────────────── */}
      <section id="prompts" className="docs-section">
        <div className="docs-sec-head">
          <h2><span className="docs-sec-num">02</span>Prompts de referencia</h2>
          <p>Prompts efectivos extraídos del documento de contexto del proyecto, categorizados por uso.</p>
        </div>

        <div className="prompt-cards">
          {PROMPT_LIBRARY.map((p, i) => (
            <div key={i} className="prompt-card">
              <div className="prompt-head">
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="prompt-ico"><p.Ico /></span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-0)" }}>{p.title}</span>
                </div>
                <button className="iconbtn" onClick={() => copy(p.prompt, `p-${i}`)} title="Copiar">
                  {copied === `p-${i}` ? <IcoCheck /> : <IcoCopy />}
                </button>
              </div>
              <div className="prompt-tag">{p.category}</div>
              <div className="prompt-body mono">{p.prompt}</div>
              <button className="prompt-try" onClick={() => { setPrompt(p.prompt); document.getElementById("playground")?.scrollIntoView({ behavior: "smooth" }); }}>
                Probar en playground →
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* ── PLAYGROUND ──────────────────────────────────────── */}
      <section id="playground" className="docs-section">
        <div className="docs-sec-head">
          <h2><span className="docs-sec-num">03</span>Playground</h2>
          <p>Probá prompts directamente sobre el contexto del proyecto. Usa <code className="inline-code">claude-haiku-4-5</code>.</p>
        </div>

        <div className="playground">
          <div className="pg-toolbar">
            <label className="pg-toggle">
              <input type="checkbox" checked={contextOn} onChange={(e) => setContextOn(e.target.checked)} />
              <span>Incluir contexto de OptiFull</span>
              <span className="pg-toggle-meta mono">{contextOn ? "+1.2k tokens" : "0 tokens"}</span>
            </label>
            <button className="pg-clear" onClick={() => { setPrompt(""); setResponse(""); }}>Limpiar</button>
          </div>

          <div className="pg-input-wrap">
            <div className="pg-msg-head">
              <span className="pg-role pg-role-user"><IcoUser size={11} stroke={2} /> Tu mensaje</span>
              <span className="mono" style={{ fontSize: 10.5, color: "var(--fg-3)" }}>{prompt.length} chars</span>
            </div>
            <textarea
              className="pg-input"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Escribí un prompt sobre OptiFull…"
              rows={4}
            />
          </div>

          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", margin: "10px 0 14px" }}>
            <button className="btn-sec" onClick={() => copy(prompt, "prompt")}>
              <IcoCopy style={{ marginRight: 6 }} />Copiar prompt
            </button>
            <button className="btn-pri" disabled={loading || !prompt.trim()} onClick={ask}>
              {loading ? <><IcoSpinner style={{ marginRight: 6, animation: "spin 1s linear infinite" }} />Pensando…</> : <><IcoSend style={{ marginRight: 6 }} />Enviar</>}
            </button>
          </div>

          {(response || loading) && (
            <div className="pg-response">
              <div className="pg-msg-head">
                <span className="pg-role pg-role-claude"><IcoSparkle size={11} stroke={2} /> Claude</span>
                {!loading && response && (
                  <button className="iconbtn" onClick={() => copy(response, "resp")}>
                    {copied === "resp" ? <IcoCheck /> : <IcoCopy />}
                  </button>
                )}
              </div>
              <div className="pg-output">
                {loading && !response ? (
                  <div className="pg-loading">
                    <span /> <span /> <span />
                  </div>
                ) : (
                  response
                )}
              </div>
            </div>
          )}

          <div className="pg-suggestions">
            <span style={{ fontSize: 11, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: ".08em" }}>Ejemplos rápidos</span>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
              {QUICK_PROMPTS.map((q, i) => (
                <button key={i} className="pg-chip" onClick={() => setPrompt(q)}>{q.split(".")[0].slice(0, 50)}…</button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── GUIDELINES ──────────────────────────────────────── */}
      <section id="guidelines" className="docs-section">
        <div className="docs-sec-head">
          <h2><span className="docs-sec-num">04</span>Guidelines de buen uso</h2>
          <p>Lo que funciona y lo que no al pedirle al asistente sobre OptiFull.</p>
        </div>

        <div className="do-dont-grid">
          <div className="do-card do">
            <div className="do-card-head"><IcoCheck2 size={14} stroke={2} /> Hacé</div>
            <ul>
              <li>Empezar con <b>"Sos asistente de OptiFull"</b> y adjuntar el PDF de contexto.</li>
              <li>Especificar <b>formato esperado</b>: tabla, código Python, lista, texto académico.</li>
              <li>Indicar <b>longitud</b> aproximada ("3 páginas", "200 palabras", "10 líneas").</li>
              <li>Usar <b>tercera persona</b> e <b>idioma español</b> para texto del informe.</li>
              <li>Citar tecnologías exactas del stack: <code className="inline-code">YOLOv8m</code>, <code className="inline-code">ByteTrack</code>, <code className="inline-code">FastAPI</code>.</li>
              <li>Pedir <b>justificación</b> de decisiones técnicas para incluir en el informe.</li>
            </ul>
          </div>
          <div className="do-card dont">
            <div className="do-card-head"><IcoX size={14} stroke={2} /> Evitá</div>
            <ul>
              <li>Pedidos vagos como "ayudame con el código" sin contexto del módulo.</li>
              <li>Asumir que la IA recuerda conversaciones anteriores — siempre re-adjuntar contexto.</li>
              <li>Salir del alcance: reconocimiento facial, integración ERP, multi-sucursal.</li>
              <li>Aceptar código sin validar contra el dominio real (cámaras, NVR Strumia).</li>
              <li>Pedir más de un módulo a la vez — fragmentar en pedidos atómicos.</li>
              <li>Copiar respuestas al informe sin <b>revisar referencias APA v7</b>.</li>
            </ul>
          </div>
        </div>
      </section>

      {/* ── CONTEXT ─────────────────────────────────────────── */}
      <section id="context" className="docs-section">
        <div className="docs-sec-head">
          <h2><span className="docs-sec-num">05</span>Contexto del proyecto</h2>
          <p>Resumen ejecutivo que se inyecta automáticamente cuando "Incluir contexto" está activado en el playground.</p>
        </div>

        <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
          <div style={{
            padding: "10px 14px", borderBottom: "1px solid var(--line)", background: "var(--bg-3)",
            display: "flex", justifyContent: "space-between", alignItems: "center"
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <IcoBook style={{ width: 14, height: 14, color: "var(--fg-2)" }} />
              <span style={{ fontSize: 12, color: "var(--fg-1)", fontWeight: 500 }}>OptiFull · contexto resumido</span>
              <span className="mono" style={{ fontSize: 10.5, color: "var(--fg-3)", padding: "1px 6px", background: "var(--bg-2)", borderRadius: 4 }}>~1200 tokens</span>
            </div>
            <button className="btn-sec" onClick={() => copy(PROJECT_CONTEXT, "ctx-full2")}>
              <IcoCopy style={{ marginRight: 6 }} />{copied === "ctx-full2" ? "Copiado!" : "Copiar"}
            </button>
          </div>
          <pre className="ctx-block">{PROJECT_CONTEXT}</pre>
        </div>

        <div style={{
          marginTop: 14, padding: "14px 18px", borderRadius: 10, background: "var(--bg-2)",
          border: "1px dashed var(--line)", fontSize: 12, color: "var(--fg-2)"
        }}>
          <b style={{ color: "var(--fg-1)" }}>Tip:</b> el documento completo está en <code className="inline-code">uploads/OptiFull_Contexto_para_IA.pdf</code>.
          Para conversaciones largas, adjuntá el PDF; para preguntas puntuales, el resumen es suficiente.
        </div>
      </section>
    </main>
  );
}

// ── Prompt library ───────────────────────────────────────────
const PROMPT_LIBRARY = [
  {
    Ico: window.IcoBook,
    title: "Marco teórico — Computer Vision",
    category: "Redacción académica",
    prompt: 'Sos asistente para mi tesis OptiFull. Adjunto el documento de contexto. Necesito que escribas la sección de Marco Teórico sobre Computer Vision y detección de objetos, aproximadamente 3 páginas, en tercera persona, estilo académico, en español, con citas en formato APA v7.',
  },
  {
    Ico: window.IcoCode,
    title: "Mapa de calor desde trayectorias",
    category: "Implementación · Python",
    prompt: 'Sos asistente de OptiFull. Ya tenemos YOLOv8 con ByteTrack funcionando. Necesito que implementes en Python un módulo que, a partir de las trayectorias detectadas, genere un mapa de calor usando OpenCV y numpy. Incluí docstring y manejo de frame_skip.',
  },
  {
    Ico: window.IcoChip,
    title: "Diagrama de arquitectura",
    category: "Diseño de sistema",
    prompt: 'Sos asistente de OptiFull. El stack es YOLOv8 + Python + FastAPI + React. Necesito el diagrama de arquitectura del sistema en formato Mermaid y la descripción de cada componente (Captura RTSP → Detección → Tracking → Métricas → API → Dashboard) para incluirla en el informe.',
  },
  {
    Ico: window.IcoCheck2,
    title: "Métricas de evaluación",
    category: "Testing y validación",
    prompt: 'Sos asistente de OptiFull. Necesito definir las métricas de evaluación para el módulo de detección de personas (precisión, recall, mAP, IoU) y para el tracking (MOTA, IDF1, ID switches). Escribilo en formato de tabla para el informe, con definición y rango de valor esperado.',
  },
  {
    Ico: window.IcoReport,
    title: "Caso de uso UML",
    category: "Diseño de sistema",
    prompt: 'Sos asistente de OptiFull. Generá los casos de uso principales del sistema en formato UML textual: actores (Encargado, Operador, Administrador YPF), casos de uso (Monitorear flujo, Recibir alertas, Generar reporte, Configurar umbrales) e incluí precondiciones, flujo principal y flujos alternativos.',
  },
  {
    Ico: window.IcoSparkle,
    title: "Conclusiones del informe",
    category: "Redacción académica",
    prompt: 'Sos asistente de OptiFull. Escribí la sección de Conclusiones y trabajo futuro del informe final, ~2 páginas, tercera persona. Incluí: lecciones aprendidas técnicas, validación con el cliente YPF, limitaciones del prototipo y líneas de trabajo futuro (multi-sucursal, integración ERP, reconocimiento de productos en playa).',
  },
];

const QUICK_PROMPTS = [
  "¿Qué métricas debería incluir en el reporte semanal de la tienda?",
  "Explicame brevemente cómo funciona ByteTrack para tracking de personas.",
  "Sugerí 3 mejoras al diseño actual del dashboard para mejorar legibilidad.",
  "¿Cuáles son los principales desafíos técnicos al implementar detección de productos en góndolas?",
  "Listame los criterios de aceptación para el módulo de detección de comportamientos sospechosos.",
];

const PROJECT_CONTEXT = `Proyecto: OptiFull — Sistema Inteligente de Análisis de Flujo y Optimización Operativa mediante Computer Vision para Tiendas FULL.
Cliente: YPF S.A. (Tiendas FULL) · Equipo: Blasón, Nahmias, Noseda, Ortiz · UCC — Proyecto Final de Carrera.

Problema: tiendas FULL enfrentan variabilidad en flujo, congestión en cajas, control manual de stock, alta rotación de personal, monitoreo manual o estimado (<10% de franquicias tiene control profesional según entrevista Martinez YPF abr/2026).

Solución: plataforma que procesa video en tiempo real desde cámaras RTSP existentes y genera métricas, alertas y reportes accionables.

Stack:
- Computer Vision: YOLOv8 (Ultralytics, yolov8m.pt) + ByteTrack + OpenCV
- Backend: Python + FastAPI
- BD: PostgreSQL / SQLite
- Frontend: React (dashboard, heatmaps, reportes)
- Protocolo cámaras: RTSP

Alcance INCLUYE: captura RTSP, detección y tracking de personas, reconocimiento de productos en góndola, mapas de calor, tiempos de permanencia y espera, detección de comportamientos sospechosos, dashboard web, almacenamiento de métricas.
Alcance EXCLUYE: reconocimiento facial, integración ERP YPF, multi-sucursal, hardware propio.

Estado mayo 2026: investigación tecnológica y primeros prototipos. Hecho: relevamiento en E.S. Strumia (Mendoza, abr/2026), entrevista Henry Martinez, pruebas YOLOv8+ByteTrack, script inicial de detección/conteo, investigación RTSP, IPI presentado 07/05/2026, cronograma Gantt feb-dic 2026.

Hitos próximos: diseño del sistema (jun), captura RTSP (jun), detección personas (jul), detección productos (jul-ago), tracking (ago), heatmaps (ago-sep), backend (sep-oct), modelo predictivo (sep-oct), interfaz web (oct-nov), integración (nov), documentación y defensa (dic 2026).

Informe final: 100-120 pgs, tercera persona, hilo conductor, secciones: resumen, presentación, glosario, diagnóstico, objetivos, marco teórico (~35 pgs), requerimientos, arquitectura, implementación, testing, conclusiones, referencias APA v7.`;

window.ClaudeDocsPage = ClaudeDocsPage;
