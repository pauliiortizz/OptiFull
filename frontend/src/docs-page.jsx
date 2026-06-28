// Documentación de Diseño — design system reference page
function DocsPage() {
  return (
    <main className="content docs">
      <div className="page-head">
        <div>
          <h1>Documentación de Diseño</h1>
          <p>Sistema de diseño, componentes y decisiones del proyecto OptiFull</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-sec"><IcoCopy style={{ marginRight: 6 }} />Exportar tokens</button>
          <button className="btn-pri">Editar</button>
        </div>
      </div>

      {/* Quick nav */}
      <div className="docs-nav">
        <a href="#design-system">Design System</a>
        <a href="#componentes">Componentes</a>
        <a href="#pantallas">Pantallas</a>
        <a href="#decisiones">Decisiones</a>
      </div>

      {/* ── DESIGN SYSTEM ─────────────────────────────────────── */}
      <section id="design-system" className="docs-section">
        <div className="docs-sec-head">
          <h2><span className="docs-sec-num">01</span>Design System</h2>
          <p>Fundamentos visuales: paleta, tipografía y espaciados.</p>
        </div>

        {/* Palette */}
        <h3 className="docs-h3">Paleta de colores</h3>
        <div className="docs-swatches">
          {[
            { name: "Azul principal", hex: "#1a3a6b", role: "Brand profundo · headers" },
            { name: "Azul medio",     hex: "#2563a8", role: "Acción primaria · acentos" },
            { name: "Verde",          hex: "#1a7a3a", role: "Positivo · stock OK · tendencia" },
            { name: "Rojo alerta",    hex: "#c0392b", role: "Alertas críticas · errores" },
            { name: "Naranja",        hex: "#d68920", role: "Warning · stock bajo" },
            { name: "Fondo claro",    hex: "#f0f4fb", role: "Background (modo claro)" },
          ].map((c) => (
            <div key={c.hex} className="swatch">
              <div className="swatch-chip" style={{ background: c.hex }}>
                <div className="swatch-overlay" />
              </div>
              <div className="swatch-meta">
                <div className="swatch-name">{c.name}</div>
                <div className="swatch-hex mono">{c.hex.toUpperCase()}</div>
                <div className="swatch-role">{c.role}</div>
              </div>
            </div>
          ))}
        </div>

        <h3 className="docs-h3" style={{ marginTop: 28 }}>Escala de superficies (modo oscuro)</h3>
        <div className="docs-surfaces">
          {[
            { v: "--bg-0", hex: "#070b14", use: "Página" },
            { v: "--bg-1", hex: "#0c1322", use: "Sidebar / chrome" },
            { v: "--bg-2", hex: "#111a2e", use: "Panel" },
            { v: "--bg-3", hex: "#172238", use: "Panel raised" },
            { v: "--bg-4", hex: "#1d2a44", use: "Hover" },
          ].map((s) => (
            <div key={s.v} className="surface">
              <div className="surface-chip" style={{ background: s.hex }} />
              <div className="mono" style={{ fontSize: 11, color: "var(--fg-1)" }}>{s.v}</div>
              <div style={{ fontSize: 10.5, color: "var(--fg-3)" }} className="mono">{s.hex}</div>
              <div style={{ fontSize: 10.5, color: "var(--fg-2)" }}>{s.use}</div>
            </div>
          ))}
        </div>

        {/* Typography */}
        <h3 className="docs-h3" style={{ marginTop: 28 }}>Tipografía</h3>
        <div className="docs-type">
          <div className="type-card">
            <div className="type-tag">UI / Texto</div>
            <div className="type-sample" style={{ fontFamily: "Geist, sans-serif" }}>
              <div style={{ fontSize: 38, fontWeight: 600, letterSpacing: "-.025em", lineHeight: 1 }}>Geist</div>
              <div style={{ fontSize: 13, color: "var(--fg-2)", marginTop: 8 }}>
                The quick brown fox jumps over the lazy dog · 0123456789
              </div>
            </div>
            <div className="type-scale">
              <div><b>H1</b><span className="mono">22 / 600</span></div>
              <div><b>H2</b><span className="mono">17 / 600</span></div>
              <div><b>H3</b><span className="mono">13 / 600</span></div>
              <div><b>Body</b><span className="mono">12.5 / 400</span></div>
              <div><b>Caption</b><span className="mono">11 / 500</span></div>
            </div>
          </div>

          <div className="type-card">
            <div className="type-tag">Datos numéricos</div>
            <div className="type-sample" style={{ fontFamily: "JetBrains Mono, monospace" }}>
              <div style={{ fontSize: 38, fontWeight: 500, letterSpacing: "-.025em", lineHeight: 1 }}>JetBrains Mono</div>
              <div style={{ fontSize: 13, color: "var(--fg-2)", marginTop: 8 }} className="mono">
                23 · 2:18 · 312 · 47% · 18:42:05
              </div>
            </div>
            <div className="type-scale">
              <div><b>KPI</b><span className="mono">34 / 500</span></div>
              <div><b>Stat</b><span className="mono">14 / 500</span></div>
              <div><b>Caption</b><span className="mono">11 / 400</span></div>
            </div>
          </div>
        </div>

        {/* Spacing + radius */}
        <h3 className="docs-h3" style={{ marginTop: 28 }}>Espaciados y bordes</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 14 }}>
          <div className="panel" style={{ padding: 18 }}>
            <div style={{ fontSize: 11, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 12 }}>Spacing scale</div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 10 }}>
              {[
                ["4",  4],
                ["8",  8],
                ["10", 10],
                ["14", 14],
                ["18", 18],
                ["22", 22],
                ["28", 28],
              ].map(([label, v]) => (
                <div key={label} style={{ textAlign: "center" }}>
                  <div style={{
                    width: v + 8, height: v + 8, background: "var(--brand-soft)", opacity: .6, borderRadius: 3, margin: "0 auto"
                  }} />
                  <div className="mono" style={{ fontSize: 10.5, color: "var(--fg-2)", marginTop: 6 }}>{label}px</div>
                </div>
              ))}
            </div>
            <div style={{ fontSize: 11, color: "var(--fg-3)", marginTop: 14 }}>
              Gap base: <b className="mono" style={{ color: "var(--fg-1)" }}>14px</b> entre paneles · <b className="mono" style={{ color: "var(--fg-1)" }}>18px</b> dentro de paneles
            </div>
          </div>

          <div className="panel" style={{ padding: 18 }}>
            <div style={{ fontSize: 11, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 12 }}>Border radius</div>
            <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
              {[
                ["sm", 6, "Chips · botones small"],
                ["md", 10, "Cajas · inputs"],
                ["lg", 14, "Paneles"],
                ["pill", 99, "Badges · barras"],
              ].map(([name, r, use]) => (
                <div key={name} style={{ textAlign: "center", flex: 1 }}>
                  <div style={{
                    width: 48, height: 48, background: "var(--bg-3)", border: "1px solid var(--line)",
                    borderRadius: r, margin: "0 auto"
                  }} />
                  <div style={{ fontSize: 11, color: "var(--fg-1)", marginTop: 8 }}>{name}</div>
                  <div className="mono" style={{ fontSize: 10, color: "var(--fg-3)" }}>{r}px</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── COMPONENTES ─────────────────────────────────────── */}
      <section id="componentes" className="docs-section">
        <div className="docs-sec-head">
          <h2><span className="docs-sec-num">02</span>Componentes</h2>
          <p>Bloques reutilizables del sistema. Cada componente con una vista previa y guía de uso.</p>
        </div>

        <div className="docs-components">
          <ComponentCard
            name="KPI Card"
            when="Métrica clave en el dashboard. Incluye valor, delta vs período y sparkline."
            preview={
              <div style={{ width: "100%" }}>
                <KpiCard
                  label="Personas en tienda" value="23" unit="ahora"
                  delta="+12% vs hace 1h" trend="up" Ico={IcoUsers}
                  spark={[12,15,18,16,21,24,22,19,23,26,28,25,22,20,24,27,30,28,24,23]}
                  color="var(--brand-soft)"
                />
              </div>
            }
          />

          <ComponentCard
            name="Sidebar Item"
            when="Navegación lateral. Estado activo con borde izquierdo y fondo gradiente."
            preview={
              <div style={{ width: 220, background: "var(--bg-1)", padding: 12, borderRadius: 10, border: "1px solid var(--line-soft)" }}>
                <nav className="nav">
                  <a className="active"><span className="ico"><IcoDashboard /></span><span>Dashboard</span></a>
                  <a><span className="ico"><IcoHeat /></span><span>Mapa de calor</span></a>
                  <a><span className="ico"><IcoAlert /></span><span>Alertas</span><span className="badge">3</span></a>
                </nav>
              </div>
            }
          />

          <ComponentCard
            name="Badge de Alerta"
            when="Indica severidad. Punto + texto + tiempo relativo. 3 niveles: crítica, warning, info."
            preview={
              <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%" }}>
                {[
                  { sev: "critical", title: "Trayectoria sospechosa", time: "12s" },
                  { sev: "warn", title: "Espera elevada en Caja 2", time: "3m" },
                  { sev: "info", title: "Pico de circulación", time: "8m" },
                ].map((a) => (
                  <div key={a.sev} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span className={`alert-dot ${a.sev}`} style={{ marginTop: 0 }} />
                    <span style={{ fontSize: 12.5, color: "var(--fg-0)" }}>{a.title}</span>
                    <span className="mono" style={{ fontSize: 10.5, color: "var(--fg-3)", marginLeft: "auto" }}>hace {a.time}</span>
                  </div>
                ))}
              </div>
            }
          />

          <ComponentCard
            name="Botones"
            when="Primario para acción principal del flujo. Secundario para acciones alternativas. Icon-only para acciones contextuales."
            preview={
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <button className="btn-pri">Generar reporte</button>
                <button className="btn-sec">Cancelar</button>
                <button className="iconbtn"><IcoMore /></button>
                <button className="iconbtn"><IcoExpand /></button>
              </div>
            }
          />

          <ComponentCard
            name="Selector de tiempo"
            when="Cambia el rango temporal de los datos. Tab activa con fondo levantado."
            preview={
              <div className="range-tabs">
                <button className="on">Hoy</button>
                <button>7 días</button>
                <button>30 días</button>
                <button>Personalizado</button>
              </div>
            }
          />

          <ComponentCard
            name="Segmented Control"
            when="Filtros mutuamente excluyentes dentro de un panel. Más compacto que tabs."
            preview={
              <div className="seg">
                <button className="on">Todas</button>
                <button>Críticas</button>
                <button>Hoy</button>
              </div>
            }
          />
        </div>
      </section>

      {/* ── PANTALLAS ─────────────────────────────────────── */}
      <section id="pantallas" className="docs-section">
        <div className="docs-sec-head">
          <h2><span className="docs-sec-num">03</span>Pantallas del sistema</h2>
          <p>Estado de implementación de cada vista del producto.</p>
        </div>

        <div className="docs-screens">
          {[
            { name: "Dashboard",      desc: "Métricas en tiempo real, flujo, alertas, mini-heatmap",        status: "done",  Ico: IcoDashboard },
            { name: "Mapa de calor",  desc: "Visualización completa del layout y zonas de circulación",      status: "wip",   Ico: IcoHeat },
            { name: "Tracking de personas", desc: "Trayectorias individuales y conteo histórico por hora",   status: "todo",  Ico: IcoTrack },
            { name: "Control de stock",    desc: "Productos detectados vs esperados, alertas de faltantes",  status: "todo",  Ico: IcoStock },
            { name: "Reportes",            desc: "Gráficos históricos exportables (PDF / CSV)",              status: "todo",  Ico: IcoReport },
            { name: "Alertas",             desc: "Panel completo de eventos sospechosos y críticos",         status: "todo",  Ico: IcoAlert },
          ].map((s) => (
            <div key={s.name} className="screen-card">
              <div className="screen-ico"><s.Ico /></div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="screen-name">{s.name}</div>
                <div className="screen-desc">{s.desc}</div>
              </div>
              <StatusPill status={s.status} />
            </div>
          ))}
        </div>

        <div style={{
          marginTop: 14, padding: "12px 16px", borderRadius: 10, background: "var(--bg-2)",
          border: "1px solid var(--line)", display: "flex", gap: 24, fontSize: 12, color: "var(--fg-2)"
        }}>
          <div><span style={{ color: "var(--pos-soft)" }}>●</span> Implementada · <b className="mono" style={{ color: "var(--fg-0)" }}>1</b></div>
          <div><span style={{ color: "var(--warn)" }}>●</span> En progreso · <b className="mono" style={{ color: "var(--fg-0)" }}>1</b></div>
          <div><span style={{ color: "var(--fg-3)" }}>●</span> Pendiente · <b className="mono" style={{ color: "var(--fg-0)" }}>4</b></div>
          <div style={{ marginLeft: "auto", color: "var(--fg-3)" }}>Avance global: <b className="mono" style={{ color: "var(--fg-1)" }}>~17%</b></div>
        </div>
      </section>

      {/* ── DECISIONES ─────────────────────────────────────── */}
      <section id="decisiones" className="docs-section">
        <div className="docs-sec-head">
          <h2><span className="docs-sec-num">04</span>Decisiones de diseño</h2>
          <p>Justificación de las elecciones clave aplicadas en el sistema.</p>
        </div>

        <div className="docs-table">
          <div className="docs-table-head">
            <div>Decisión</div>
            <div>Justificación</div>
          </div>
          {[
            ["Tema oscuro por defecto",
             "Reduce fatiga visual en monitoreo continuo. La sala de operaciones tiende a tener iluminación tenue y el contraste alto sobre fondo oscuro destaca alertas críticas sin saturar la vista."],
            ["Tipografía monoespaciada para datos numéricos",
             "Evita 'saltos' visuales cuando los valores se actualizan en tiempo real. JetBrains Mono mantiene ancho constante por dígito, esencial en KPIs y timestamps que cambian cada segundo."],
            ["Sparklines en cada KPI",
             "Comunican tendencia inmediata sin requerir un gráfico completo. En una pantalla densa, el ojo capta la dirección del valor en menos de 200ms — algo imposible con sólo el delta numérico."],
            ["Rojo reservado exclusivamente para alertas críticas",
             "Evita la 'fatiga de alerta'. Si todo es rojo, nada es rojo. Warning usa naranja, info usa azul brand. Sólo eventos que requieren intervención inmediata reciben el rojo."],
            ["Indicador de pulso en hora actual del gráfico",
             "Refuerza la percepción de que el dashboard está vivo. La animación periódica del marcador comunica 'datos frescos' sin necesidad de un timestamp explícito."],
            ["Forecast con línea punteada",
             "Diferencia visualmente datos medidos de datos proyectados. El usuario operativo nunca debe confundir una proyección con una medición real al tomar decisiones."],
            ["Sidebar fijo con secciones agrupadas",
             "Mantiene el contexto operativo siempre visible. Agrupar por 'Monitoreo', 'Análisis' y 'Sistema' reduce la carga cognitiva al navegar entre módulos con propósitos distintos."],
            ["Sucursal y estado de cámaras siempre en topbar",
             "Permite supervisar varias sucursales sin perder de vista cuál se está observando. El indicador 'LIVE' confirma que el pipeline RTSP → YOLOv8 está activo."],
            ["Densidad alta de información",
             "El usuario es un operador profesional, no un consumidor. Maximizar señal por píxel evita scroll en una pantalla de supervisión que típicamente vive en un monitor fijo."],
            ["Layout de tienda esquemático en heatmap",
             "Un blueprint abstracto es más legible que una imagen fotorrealista del local. Las zonas (entrada, góndolas, cajas) se identifican por posición y etiqueta, no por textura."],
          ].map(([d, j], i) => (
            <div key={i} className="docs-table-row">
              <div><b>{d}</b></div>
              <div>{j}</div>
            </div>
          ))}
        </div>
      </section>

      <div style={{
        marginTop: 28, padding: "14px 18px", borderRadius: 10, background: "var(--bg-2)",
        border: "1px dashed var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center"
      }}>
        <div style={{ fontSize: 12, color: "var(--fg-2)" }}>
          Última actualización: <span className="mono" style={{ color: "var(--fg-1)" }}>14 may 2026 · 18:42</span>
          <span style={{ color: "var(--fg-4)", margin: "0 10px" }}>·</span>
          Versión: <span className="mono" style={{ color: "var(--fg-1)" }}>v0.3.0</span>
        </div>
        <div style={{ fontSize: 11.5, color: "var(--fg-3)" }}>
          Equipo: Blasón · Nahmias · Noseda · Ortiz
        </div>
      </div>
    </main>
  );
}

function ComponentCard({ name, when, preview }) {
  return (
    <div className="comp-card">
      <div className="comp-preview">{preview}</div>
      <div className="comp-meta">
        <div className="comp-name">{name}</div>
        <div className="comp-when">{when}</div>
      </div>
    </div>
  );
}

function StatusPill({ status }) {
  const map = {
    done: { label: "Implementada",  color: "var(--pos-soft)",  bg: "rgba(46,163,79,.1)",  border: "rgba(46,163,79,.25)", Ico: IcoCheck },
    wip:  { label: "En progreso",   color: "var(--warn)",       bg: "rgba(214,137,32,.1)", border: "rgba(214,137,32,.28)", Ico: IcoSpinner },
    todo: { label: "Pendiente",     color: "var(--fg-2)",       bg: "var(--bg-3)",         border: "var(--line)", Ico: IcoTodo },
  };
  const s = map[status];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: "4px 10px", borderRadius: 99, fontSize: 11.5, fontWeight: 500,
      color: s.color, background: s.bg, border: `1px solid ${s.border}`, whiteSpace: "nowrap"
    }}>
      <s.Ico size={12} stroke={2} />
      {s.label}
    </span>
  );
}

window.DocsPage = DocsPage;
