// Promedio real de personas detectadas por dia de la semana (suma todos los
// videos analizados de una misma fecha calendario, y promedia esos totales
// entre todas las fechas que cayeron en cada dia de la semana).
function useTendenciaSemanal() {
  const [data, setData]       = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    fetch('/api/reportes/tendencia-semanal')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  return { data, loading };
}

// Permanencia real promedio (minutos) por dia de la semana (ver
// /reportes/permanencia-semanal en el backend: promedia el tiempo real de
// permanencia por cliente y dia, y luego entre todas las fechas que cayeron
// en cada dia de la semana).
function usePermanenciaSemanal() {
  const [data, setData]       = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    fetch('/api/reportes/permanencia-semanal')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  return { data, loading };
}

// Promedio de personas unicas detectadas por dia (sumatoria de clientes
// distintos por fecha, promediada entre los dias con datos). Por ahora solo
// camara 4; se combinara con las demas camaras a futuro.
function usePromedioDiario() {
  const [data, setData]       = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    fetch('/api/reportes/promedio-diario')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  return { data, loading };
}

// Candidatos a "empleado" por heuristica de permanencia total diaria (ver
// UMBRAL_HORAS_POSIBLE_EMPLEADO en el backend). Son solo sugerencias: hay
// que confirmarlas a mano, nunca se excluyen solas de las metricas.
function usePosiblesEmpleados() {
  const [data, setData]       = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const refresh = React.useCallback(() => {
    setLoading(true);
    fetch('/api/reportes/posibles-empleados')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  React.useEffect(() => { refresh(); }, [refresh]);
  return { data, loading, refresh };
}

// Promedio diario de clientes reales que COMPRARON vs. que NO compraron
// nada (ver /reportes/conversion-compra en el backend: clasificacion
// Escenario A/B/C de deteccion/pipeline/eventos.py, tabla 'eventos').
function useConversionCompra() {
  const [data, setData]       = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    fetch('/api/reportes/conversion-compra')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  return { data, loading };
}

// Permanencia real por zona (Caja/Gondolas/Salon) -- minutos promedio por
// visitante, estimado a partir de los puntos de trayectoria de cada zona.
function usePermanenciaPorZona() {
  const [data, setData]       = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    fetch('/api/reportes/permanencia-por-zona')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  return { data, loading };
}

// Horarios estimados de congestion: cuanta gente (personas unicas) hubo en
// camara por franja horaria, dia por dia de la semana (ver
// /reportes/congestion-horaria en el backend, que usa 'visitas' para no
// contar huecos y promedia entre todas las fechas de cada dia de semana).
function useCongestionHoraria() {
  const [data, setData]       = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    fetch('/api/reportes/congestion-horaria')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  return { data, loading };
}

// REPORTS PAGE
function ReportsPage() {
  const toast = useToast();
  const [range, setRange] = React.useState("7d");
  const [metric, setMetric] = React.useState("flow");
  const { stats, loading, refresh }                 = useApiStats();
  const { data: tendencia, loading: loadingTend }    = useTendenciaSemanal();
  const { data: permanenciaSemanal, loading: loadingPermSemanal } = usePermanenciaSemanal();
  const { data: promedioDiario }                     = usePromedioDiario();
  const { data: congestion, loading: loadingCongestion } = useCongestionHoraria();
  const { data: permanenciaZona, loading: loadingPermanenciaZona } = usePermanenciaPorZona();
  const { data: conversion, loading: loadingConversion } = useConversionCompra();
  const { data: posiblesEmpleados, refresh: refreshEmpleados } = usePosiblesEmpleados();
  const [marcando, setMarcando] = React.useState(null);

  const marcarEmpleado = (clienteId) => {
    setMarcando(clienteId);
    fetch(`/api/personas/${clienteId}/empleado`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ es_empleado: true }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) { toast(d.error, { kind: "warn" }); return; }
        toast(`Cliente ${clienteId} marcado como empleado — excluido de las métricas`, { kind: "success" });
        refreshEmpleados();
        refresh();
      })
      .catch(() => toast("No se pudo marcar como empleado", { kind: "warn" }))
      .finally(() => setMarcando(null));
  };

  const days              = tendencia?.labels || ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"];
  const flowWeek          = tendencia?.promedio || [0,0,0,0,0,0,0];
  const diasConDatos      = tendencia?.dias_con_datos || [0,0,0,0,0,0,0];
  const waitWeek          = permanenciaSemanal?.promedio || [0,0,0,0,0,0,0];
  const diasConDatosEspera = permanenciaSemanal?.dias_con_datos || [0,0,0,0,0,0,0];

  const data = metric === "flow" ? flowWeek : waitWeek;

  const total = data.reduce((a,b) => a+b, 0);
  const avg = Math.round(total / data.length);
  const peak = Math.max(...data);
  const peakDay = days[data.indexOf(peak)];

  const exportFmt = (fmt) => {
    toast(`Generando ${fmt.toUpperCase()}…`, { kind: "info" });
    window.location.href = `/api/export/${fmt}`;
  };

  return (
    <main className="content docs">
      <PageHeader
        title="Reportes"
        subtitle="Análisis histórico y exportación de métricas operativas."
        right={
          <>
            <div className="range-tabs">
              {[["24h","24h"],["7d","7 días"],["30d","30 días"],["90d","90 días"]].map(([k,l]) => (
                <button key={k} className={range===k?"on":""} onClick={() => setRange(k)}>{l}</button>
              ))}
            </div>
            <button className="btn-sec" onClick={refresh} disabled={loading} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <IcoSpinner style={{ width: 13, height: 13, animation: loading ? "spin 1s linear infinite" : "none" }} />
              {loading ? "Actualizando…" : "Actualizar datos"}
            </button>
            <button className="btn-sec" onClick={() => exportFmt("csv")}><IcoDownload style={{ marginRight: 6 }} />CSV</button>
            <button className="btn-pri" onClick={() => exportFmt("pdf")}><IcoDownload style={{ marginRight: 6 }} />Reporte PDF</button>
          </>
        }
      />

      {/* Summary */}
      <div className="kpi-grid">
        <KpiCard label="Personas analizadas" value={stats ? stats.personas_unicas : "—"} unit="únicas"
          delta={stats ? `${stats.personas_totales} registros · ${stats.fuente.toUpperCase()}` : "cargando…"} trend="neutral" Ico={IcoUsers}
          spark={flowWeek} color="var(--brand-soft)" />
        <KpiCard label="Permanencia promedio" value={stats ? stats.permanencia_promedio_min : "—"} unit="min"
          delta={stats ? `${stats.personas_validas} registros válidos` : "cargando…"} trend="neutral" Ico={IcoClock} iconClass="pos"
          spark={waitWeek} color="var(--pos-soft)" />
        <KpiCard label="Permanencia máxima" value={stats ? stats.permanencia_maxima_min : "—"} unit="min"
          delta="por grabación analizada" trend="neutral" Ico={IcoTrend}
          spark={flowWeek} color="var(--brand-soft)" />
        <KpiCard label="Promedio diario" value={promedioDiario?.promedio ?? "N/D"} unit={promedioDiario?.promedio != null ? "únicas" : ""}
          delta={promedioDiario?.promedio != null
            ? `${promedioDiario.dias_con_datos} día${promedioDiario.dias_con_datos === 1 ? "" : "s"} · todas las cámaras`
            : "requiere múltiples sesiones"} trend="neutral" Ico={IcoCalendar}
          spark={flowWeek} color="var(--fg-3)" />
      </div>

      {/* Main chart */}
      <div className="panel" style={{ marginTop: 14 }}>
        <div className="panel-head">
          <div>
            <div className="panel-title"><span className="ico"><IcoTrend /></span>Tendencia semanal</div>
            <div style={{ fontSize: 11.5, color: "var(--fg-3)", marginTop: 4 }}>
              {metric === "flow"
                ? (loadingTend ? "Cargando promedio histórico…" : "Promedio histórico por día de la semana · datos reales")
                : (loadingPermSemanal ? "Cargando promedio histórico…" : "Permanencia promedio (min) por día de la semana · datos reales")}
            </div>
          </div>
          <div className="seg">
            <button className={metric==="flow"?"on":""} onClick={() => setMetric("flow")}>Flujo</button>
            <button className={metric==="wait"?"on":""} onClick={() => setMetric("wait")}>Espera</button>
          </div>
        </div>
        <BarChart data={data} labels={days} diasConDatos={metric === "flow" ? diasConDatos : diasConDatosEspera} />
      </div>

      {/* Horario de congestion (dia x hora) */}
      <div className="panel" style={{ marginTop: 14 }}>
        <div className="panel-head">
          <div>
            <div className="panel-title"><span className="ico"><IcoHeat /></span>Horario de congestión</div>
            <div style={{ fontSize: 11.5, color: "var(--fg-3)", marginTop: 4 }}>
              {loadingCongestion
                ? "Cargando…"
                : congestion?.pico
                  ? (() => {
                      const p = congestion.pico;
                      const rango = `${String(p.hora_inicio).padStart(2,"0")}-${String((p.hora_fin+1)%24).padStart(2,"0")}hs`;
                      const extra = congestion.picos.length > 1 ? ` · +${congestion.picos.length - 1} pico${congestion.picos.length - 1 === 1 ? "" : "s"} más (un mismo día puede tener varios)` : "";
                      return `Pico más alto: ${p.dia} ${rango} · ${p.promedio} personas en promedio${extra}`;
                    })()
                  : "Personas en cámara por franja horaria, día por día · sin datos suficientes todavía"}
            </div>
          </div>
        </div>
        {congestion && <CongestionHeatmap data={congestion} />}
      </div>

      {/* Zone breakdown + Top alerts */}
      <div className="main-grid" style={{ marginTop: 14 }}>
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title"><span className="ico"><IcoHeat /></span>Permanencia por zona</div>
            <span className="mono" style={{ fontSize: 11, color: "var(--fg-3)" }}>min/visitante</span>
          </div>
          {loadingPermanenciaZona && (
            <div style={{ padding: "20px 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12 }}>
              Cargando…
            </div>
          )}
          {!loadingPermanenciaZona && !permanenciaZona?.zonas?.length && (
            <div style={{ padding: "20px 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12 }}>
              Sin datos todavía -- analizá algún video para ver la permanencia real por zona.
            </div>
          )}
          {!loadingPermanenciaZona && permanenciaZona?.zonas?.length > 0 && (() => {
            const max = Math.max(...permanenciaZona.zonas.map(z => z.minutos_por_visitante), 0.1);
            return (
              <div className="zone-bars">
                {permanenciaZona.zonas.map(z => (
                  <div key={z.tipo} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <div className="zone-bar-row">
                      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--fg-1)", width: 100 }}>{z.nombre}</div>
                      <div style={{ flex: 1, height: 22, position: "relative" }}>
                        <div style={{
                          width: `${(z.minutos_por_visitante/max)*100}%`, height: "100%",
                          background: `linear-gradient(90deg, var(--brand) 0%, var(--brand-soft) 100%)`,
                          borderRadius: 5, opacity: .85
                        }} />
                      </div>
                      <div className="mono" style={{ width: 48, textAlign: "right", color: "var(--fg-3)", fontSize: 13 }}>{z.pct}%</div>
                    </div>
                    <div className="mono" style={{ marginLeft: 112, fontSize: 14, color: "var(--fg-1)" }}>
                      <b>{z.permanencia_promedio_min.toFixed(1)}m</b> prom{"  ·  "}
                      <b>{z.permanencia_maxima_min.toFixed(1)}m</b> máx{"  ·  "}
                      <span style={{ color: "var(--fg-3)" }}>{z.visitantes} visitantes</span>
                    </div>
                  </div>
                ))}
              </div>
            );
          })()}
        </div>

        <div className="panel">
          <div className="panel-head">
            <div className="panel-title"><span className="ico"><IcoAlert /></span>Alertas del período</div>
            <span className="mono" style={{ fontSize: 11, color: "var(--fg-3)" }}>72 totales</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              { label: "Trayectorias sospechosas",   count: 6,  sev: "critical" },
              { label: "Stock crítico",              count: 14, sev: "critical" },
              { label: "Cola excesiva en caja",      count: 22, sev: "warn"     },
              { label: "Aglomeraciones",             count: 8,  sev: "warn"     },
              { label: "Permanencias prolongadas",   count: 15, sev: "info"     },
              { label: "Picos de circulación",       count: 7,  sev: "info"     },
            ].map(a => (
              <div key={a.label} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span className={`alert-dot ${a.sev}`} style={{ marginTop: 0 }} />
                <span style={{ fontSize: 12.5, color: "var(--fg-1)", flex: 1 }}>{a.label}</span>
                <div style={{ width: 100, height: 5, background: "var(--bg-3)", borderRadius: 99 }}>
                  <div style={{
                    width: `${(a.count/22)*100}%`, height: "100%",
                    background: a.sev==="critical" ? "var(--alert-soft)" : a.sev==="warn" ? "var(--warn)" : "var(--brand-soft)",
                    borderRadius: 99
                  }} />
                </div>
                <span className="mono" style={{ width: 28, textAlign: "right", fontSize: 12, color: "var(--fg-0)", fontWeight: 500 }}>{a.count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Conversion de compra: promedio diario de clientes que compraron vs. no */}
      <div className="panel" style={{ marginTop: 14 }}>
        <div className="panel-head">
          <div>
            <div className="panel-title"><span className="ico"><IcoUsers /></span>Conversión de compra</div>
            <div style={{ fontSize: 11.5, color: "var(--fg-3)", marginTop: 4 }}>
              {loadingConversion
                ? "Cargando…"
                : conversion?.dias_con_datos
                  ? `Promedio diario · ${conversion.dias_con_datos} día${conversion.dias_con_datos === 1 ? "" : "s"} con datos · Escenario A/B/C (deteccion/pipeline/eventos.py)`
                  : "Sin datos todavía -- analizá algún video para clasificar visitas como compra o tránsito."}
            </div>
          </div>
          {conversion?.pct_conversion != null && (
            <span className="mono" style={{ fontSize: 20, fontWeight: 600, color: "var(--pos-soft)" }}>
              {conversion.pct_conversion}%
            </span>
          )}
        </div>
        {!loadingConversion && conversion?.dias_con_datos > 0 && (() => {
          const compraron    = conversion.promedio_compraron;
          const noCompraron  = conversion.promedio_no_compraron;
          const max          = Math.max(compraron, noCompraron, 1);
          const filas = [
            { label: "Compraron",     valor: compraron,   color: "var(--pos-soft)" },
            { label: "No compraron",  valor: noCompraron, color: "var(--fg-3)" },
          ];
          return (
            <div className="zone-bars">
              {filas.map(f => (
                <div key={f.label} className="zone-bar-row">
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--fg-1)", width: 110 }}>{f.label}</div>
                  <div style={{ flex: 1, height: 22, position: "relative" }}>
                    <div style={{
                      width: `${(f.valor / max) * 100}%`, height: "100%",
                      background: f.color, borderRadius: 5, opacity: .85,
                    }} />
                  </div>
                  <div className="mono" style={{ width: 60, textAlign: "right", color: "var(--fg-1)", fontSize: 14, fontWeight: 500 }}>
                    {f.valor} / día
                  </div>
                </div>
              ))}
            </div>
          );
        })()}
      </div>

      {/* Posibles empleados (heuristica de permanencia diaria) */}
      {posiblesEmpleados?.candidatos?.length > 0 && (
        <div className="panel" style={{ marginTop: 14 }}>
          <div className="panel-head">
            <div>
              <div className="panel-title"><span className="ico"><IcoUsers /></span>Posibles empleados</div>
              <div style={{ fontSize: 11.5, color: "var(--fg-3)", marginTop: 4 }}>
                Clientes con más de {posiblesEmpleados.umbral_horas}h detectadas en un mismo día · confirmá para excluirlos de las métricas
              </div>
            </div>
          </div>
          <div className="data-table" style={{ border: 0 }}>
            <div className="dt-head dt-row dt-empleados">
              <div>Cliente</div>
              <div>Fecha</div>
              <div>Apariciones</div>
              <div>Tiempo total</div>
              <div>Rango horario</div>
              <div></div>
            </div>
            {posiblesEmpleados.candidatos.map(c => (
              <div key={`${c.cliente_id}-${c.fecha}`} className="dt-row dt-empleados">
                <div className="mono" style={{ color: "var(--fg-0)" }}>#{c.cliente_id}</div>
                <div className="mono" style={{ color: "var(--fg-2)" }}>{c.fecha}</div>
                <div className="mono" style={{ color: "var(--fg-2)" }}>{c.apariciones}</div>
                <div className="mono" style={{ color: "var(--fg-1)" }}>{Math.floor(c.minutos_totales/60)}h {c.minutos_totales%60}m</div>
                <div className="mono" style={{ color: "var(--fg-2)" }}>{c.primera_hora.slice(0,5)}–{c.ultima_hora.slice(0,5)}</div>
                <div>
                  <button className="btn-sec" disabled={marcando === c.cliente_id} onClick={() => marcarEmpleado(c.cliente_id)}>
                    {marcando === c.cliente_id ? "Marcando…" : "Marcar como empleado"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Historical table */}
      <div className="panel" style={{ marginTop: 14 }}>
        <div className="panel-head">
          <div className="panel-title"><span className="ico"><IcoReport /></span>Detalle diario</div>
          <button className="btn-sec" onClick={() => exportFmt("xlsx")}>
            <IcoDownload style={{ marginRight: 6 }} />XLSX
          </button>
        </div>
        <div className="data-table" style={{ border: 0 }}>
          <div className="dt-head dt-row dt-reports">
            <div>Día</div>
            <div>Visitantes</div>
            <div>Pico</div>
            <div>Espera prom.</div>
            <div>Alertas</div>
            <div>Conversión est.</div>
          </div>
          {days.map((d, i) => (
            <div key={d} className="dt-row dt-reports">
              <div style={{ color: "var(--fg-0)", fontWeight: 500 }}>{d}</div>
              <div className="mono" style={{ color: "var(--fg-1)" }}>{flowWeek[i]}</div>
              <div className="mono" style={{ color: "var(--fg-2)" }}>{16 + i}:{['00','15','30','45','00','30','15'][i]}</div>
              <div className="mono" style={{ color: "var(--fg-2)" }}>{Math.floor(waitWeek[i]/60)}:{(waitWeek[i]%60).toString().padStart(2,"0")}</div>
              <div className="mono" style={{ color: "var(--fg-2)" }}>{Math.round(8 + Math.random()*6)}</div>
              <div className="mono" style={{ color: "var(--pos-soft)" }}>{(62 + i*1.4).toFixed(1)}%</div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}

function BarChart({ data, labels, diasConDatos }) {
  const W = 760, H = 240, PAD_L = 40, PAD_R = 12, PAD_T = 16, PAD_B = 30;
  const innerW = W - PAD_L - PAD_R, innerH = H - PAD_T - PAD_B;
  const max = Math.max(1, ...data) * 1.15;
  const bw = innerW / data.length * 0.4;
  const groupW = innerW / data.length;

  const yTicks = 4;
  const ticks = Array.from({ length: yTicks + 1 }, (_, i) => Math.round((max / yTicks) * i));
  const yAt = (v) => PAD_T + innerH - (v / max) * innerH;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }} preserveAspectRatio="none">
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={PAD_L} x2={W - PAD_R} y1={yAt(t)} y2={yAt(t)}
            stroke="var(--line-soft)" strokeDasharray={i === 0 ? "0" : "2 4"} />
          <text x={PAD_L - 8} y={yAt(t) + 3} textAnchor="end" fontSize="10"
            fill="var(--fg-3)" fontFamily="JetBrains Mono">{t}</text>
        </g>
      ))}
      {labels.map((l, i) => {
        const cx  = PAD_L + groupW * i + groupW / 2;
        const n   = diasConDatos ? diasConDatos[i] : null;
        const sinDatos = n === 0;
        return (
          <g key={l}>
            <text x={cx} y={H - 18} textAnchor="middle" fontSize="11"
              fill="var(--fg-2)" fontFamily="Geist">{l}</text>
            {n != null && (
              <text x={cx} y={H - 6} textAnchor="middle" fontSize="9"
                fill="var(--fg-3)" fontFamily="JetBrains Mono">
                {sinDatos ? "sin datos" : `${n} día${n === 1 ? "" : "s"}`}
              </text>
            )}
            <rect x={cx - bw/2} y={yAt(data[i])} width={bw} height={H - PAD_B - yAt(data[i])}
              fill={sinDatos ? "var(--fg-3)" : "var(--brand-soft)"} opacity={sinDatos ? .25 : 1} rx="2">
              <animate attributeName="height" from="0" to={H - PAD_B - yAt(data[i])} dur=".5s" />
              <animate attributeName="y" from={H - PAD_B} to={yAt(data[i])} dur=".5s" />
            </rect>
            {!sinDatos && (
              <text x={cx} y={yAt(data[i]) - 4} textAnchor="middle"
                fontSize="10" fill="var(--fg-1)" fontFamily="JetBrains Mono" fontWeight="500">{data[i]}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// Rampa secuencial (un solo hue, magnitud baja->alta) tomada de la paleta de
// diseño validada -- pasos 100->700, mismo azul de marca de la app
// (--brand/--brand-soft son casi identicos a los pasos 450/500). Convencion
// pedida: mas gente = color mas intenso/saturado (oscuro); menos gente =
// color mas claro/palido.
const HEAT_RAMP = [
  "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
  "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b",
];

function colorHeat(value, max) {
  if (max <= 0) return HEAT_RAMP[0];
  const t = Math.min(1, Math.max(0, value / max));
  return HEAT_RAMP[Math.round(t * (HEAT_RAMP.length - 1))];
}

function CongestionHeatmap({ data }) {
  const { dias, horas, matriz, dias_con_datos, picos } = data;
  const W = 760, PAD_L = 34, PAD_R = 8, PAD_T = 16, PAD_B = 30;
  const GAP = 2, ROW_H = 22, COL_W = (W - PAD_L - PAD_R - (horas.length - 1) * GAP) / horas.length;
  const H = PAD_T + dias.length * ROW_H + (dias.length - 1) * GAP + PAD_B;

  const max = Math.max(0, ...matriz.flat());
  const xAt = (h) => PAD_L + h * (COL_W + GAP);
  const yAt = (i) => PAD_T + i * (ROW_H + GAP);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }} preserveAspectRatio="none">
      {horas.map((h) => h % 3 === 0 && (
        <text key={h} x={xAt(h) + COL_W / 2} y={PAD_T - 5} textAnchor="middle" fontSize="9"
          fill="var(--fg-3)" fontFamily="JetBrains Mono">{h}</text>
      ))}
      {dias.map((dia, i) => (
        <text key={dia} x={PAD_L - 6} y={yAt(i) + ROW_H / 2 + 3} textAnchor="end" fontSize="10.5"
          fill="var(--fg-2)" fontFamily="Geist">{dia}</text>
      ))}
      {dias.map((dia, i) => horas.map((h) => {
        const valor    = matriz[i][h];
        const conDatos = dias_con_datos[i][h] > 0;
        // Un dia puede tener MAS DE UN pico (manana y tarde, por ej.) --
        // se resalta cualquier celda que caiga dentro de alguno de ellos,
        // no solo la del pico mas alto de toda la semana.
        const esPico   = (picos || []).some(p => p.dia === dia && h >= p.hora_inicio && h <= p.hora_fin);
        return (
          <rect key={`${i}-${h}`} className="heat-cell"
            x={xAt(h)} y={yAt(i)} width={COL_W} height={ROW_H} rx="3"
            fill={conDatos ? colorHeat(valor, max) : "var(--bg-3)"}
            stroke={esPico ? "var(--fg-0)" : conDatos ? "none" : "var(--line-soft)"}
            strokeWidth={esPico ? 1.5 : 1}
          >
            <title>
              {`${dia} ${String(h).padStart(2, "0")}-${String((h + 1) % 24).padStart(2, "0")}hs — `
                + (conDatos ? `${valor} personas en promedio (${dias_con_datos[i][h]} día${dias_con_datos[i][h] === 1 ? "" : "s"})` : "sin datos")}
            </title>
          </rect>
        );
      }))}
      {/* Leyenda: rampa secuencial baja -> alta */}
      <defs>
        <linearGradient id="heatLegendGrad" x1="0" y1="0" x2="1" y2="0">
          {HEAT_RAMP.map((c, i) => (
            <stop key={i} offset={`${(i / (HEAT_RAMP.length - 1)) * 100}%`} stopColor={c} />
          ))}
        </linearGradient>
      </defs>
      <text x={PAD_L} y={H - 6} fontSize="9.5" fill="var(--fg-3)" fontFamily="Geist">menos gente</text>
      <rect x={PAD_L + 68} y={H - 15} width={110} height={8} rx="4" fill="url(#heatLegendGrad)" />
      <text x={PAD_L + 184} y={H - 6} fontSize="9.5" fill="var(--fg-3)" fontFamily="Geist">más gente</text>
    </svg>
  );
}

window.ReportsPage = ReportsPage;
