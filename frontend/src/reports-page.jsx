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

// REPORTS PAGE
function ReportsPage() {
  const toast = useToast();
  const [range, setRange] = React.useState("7d");
  const [metric, setMetric] = React.useState("flow");
  const { stats, loading, refresh }                 = useApiStats();
  const { data: tendencia, loading: loadingTend }    = useTendenciaSemanal();

  const days           = tendencia?.labels || ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"];
  const flowWeek        = tendencia?.promedio || [0,0,0,0,0,0,0];
  const diasConDatos    = tendencia?.dias_con_datos || [0,0,0,0,0,0,0];
  const waitWeek = [180, 175, 190, 210, 245, 280, 230]; // TODO: sin implementar con datos reales todavia

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
        <KpiCard label="Personas analizadas" value={stats ? stats.personas_totales : "—"} unit="registros"
          delta={stats ? `Fuente: ${stats.fuente.toUpperCase()}` : "cargando…"} trend="neutral" Ico={IcoUsers}
          spark={flowWeek} color="var(--brand-soft)" />
        <KpiCard label="Permanencia promedio" value={stats ? stats.permanencia_promedio_min : "—"} unit="min"
          delta={stats ? `${stats.personas_validas} registros válidos` : "cargando…"} trend="neutral" Ico={IcoClock} iconClass="pos"
          spark={waitWeek} color="var(--pos-soft)" />
        <KpiCard label="Permanencia máxima" value={stats ? stats.permanencia_maxima_min : "—"} unit="min"
          delta="por grabación analizada" trend="neutral" Ico={IcoTrend}
          spark={flowWeek} color="var(--brand-soft)" />
        <KpiCard label="Promedio diario" value="N/D" unit=""
          delta="requiere múltiples sesiones" trend="neutral" Ico={IcoCalendar}
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
                : "Promedio histórico por día de la semana"}
            </div>
          </div>
          <div className="seg">
            <button className={metric==="flow"?"on":""} onClick={() => setMetric("flow")}>Flujo</button>
            <button className={metric==="wait"?"on":""} onClick={() => setMetric("wait")}>Espera</button>
            <button onClick={() => toast("Métrica 'Conversión' próximamente")}>Conversión</button>
          </div>
        </div>
        <BarChart data={data} labels={days} diasConDatos={metric === "flow" ? diasConDatos : null} />
      </div>

      {/* Zone breakdown + Top alerts */}
      <div className="main-grid" style={{ marginTop: 14 }}>
        <div className="panel">
          <div className="panel-head">
            <div className="panel-title"><span className="ico"><IcoHeat /></span>Permanencia por zona</div>
            <span className="mono" style={{ fontSize: 11, color: "var(--fg-3)" }}>min/visitante</span>
          </div>
          <div className="zone-bars">
            {[
              ["Cafetería", 3.8, 28],
              ["Góndolas centro", 2.4, 22],
              ["Cajas", 2.1, 18],
              ["Heladera", 1.6, 14],
              ["Entrada", 0.4, 12],
              ["Playa", 4.2, 6],
            ].map(([z, t, pct], i) => (
              <div key={z} className="zone-bar-row">
                <div style={{ fontSize: 12, color: "var(--fg-1)", width: 130 }}>{z}</div>
                <div style={{ flex: 1, height: 18, position: "relative" }}>
                  <div style={{
                    width: `${(t/4.5)*100}%`, height: "100%",
                    background: `linear-gradient(90deg, var(--brand) 0%, var(--brand-soft) 100%)`,
                    borderRadius: 4, opacity: .85
                  }} />
                  <div style={{
                    position: "absolute", left: `calc(${(t/4.5)*100}% + 8px)`, top: 2,
                    fontSize: 11, color: "var(--fg-1)"
                  }} className="mono">{t.toFixed(1)}m</div>
                </div>
                <div className="mono" style={{ width: 44, textAlign: "right", color: "var(--fg-3)", fontSize: 11 }}>{pct}%</div>
              </div>
            ))}
          </div>
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

window.ReportsPage = ReportsPage;
