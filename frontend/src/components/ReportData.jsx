import React from 'react'

// Hooks de datos y gráficos de las métricas de reportes que muestra el Dashboard.
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

function BarChart({ data, labels, diasConDatos }) {
  const W = 640, H = 330, PAD_L = 44, PAD_R = 8, PAD_T = 26, PAD_B = 50;
  const innerW = W - PAD_L - PAD_R, innerH = H - PAD_T - PAD_B;
  const max = Math.max(1, ...data) * 1.15;
  const bw = innerW / data.length * 0.55;
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
          <text x={PAD_L - 8} y={yAt(t) + 3} textAnchor="end" fontSize="15"
            fill="var(--fg-2)" fontFamily="var(--font-metric)">{t}</text>
        </g>
      ))}
      {labels.map((l, i) => {
        const cx  = PAD_L + groupW * i + groupW / 2;
        const n   = diasConDatos ? diasConDatos[i] : null;
        const sinDatos = n === 0;
        return (
          <g key={l}>
            <text x={cx} y={H - 28} textAnchor="middle" fontSize="16" fontWeight="500"
              fill="var(--fg-1)" fontFamily="var(--font-ui)">{l}</text>
            {n != null && (
              <text x={cx} y={H - 8} textAnchor="middle" fontSize="13"
                fill="var(--fg-3)" fontFamily="var(--font-metric)">
                {sinDatos ? "sin datos" : `${n} día${n === 1 ? "" : "s"}`}
              </text>
            )}
            <rect x={cx - bw/2} y={yAt(data[i])} width={bw} height={H - PAD_B - yAt(data[i])}
              fill={sinDatos ? "var(--fg-3)" : "var(--brand-soft)"} opacity={sinDatos ? .25 : 1} rx="4">
              <animate attributeName="height" from="0" to={H - PAD_B - yAt(data[i])} dur=".5s" />
              <animate attributeName="y" from={H - PAD_B} to={yAt(data[i])} dur=".5s" />
            </rect>
            {!sinDatos && (
              <text x={cx} y={yAt(data[i]) - 6} textAnchor="middle"
                fontSize="16" fill="var(--fg-0)" fontFamily="var(--font-metric)" fontWeight="600">{data[i]}</text>
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

// Color continuo sobre la misma rampa (interpola entre pasos vecinos) para que
// la franja cambie de tono de forma gradual y no a saltos.
function hexRgb(h) { return [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)) }
function colorHeatSuave(value, max) {
  if (max <= 0) return HEAT_RAMP[0];
  const t = Math.min(1, Math.max(0, value / max)) * (HEAT_RAMP.length - 1);
  const i = Math.min(HEAT_RAMP.length - 2, Math.floor(t));
  const f = t - i;
  const [a, b] = [hexRgb(HEAT_RAMP[i]), hexRgb(HEAT_RAMP[i + 1])];
  return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(",")})`;
}

// Una franja continua por dia: el color va cambiando hora a hora segun cuanta
// gente hubo (mas intenso = mas gente). Las horas sin datos quedan en gris.
function CongestionHeatmap({ data }) {
  const { dias, horas, matriz, dias_con_datos } = data;
  const W = 640, PAD_L = 42, PAD_R = 6, PAD_T = 26, PAD_B = 44;
  const ROW_H = 30, GAP = 8;
  const innerW = W - PAD_L - PAD_R;
  const COL_W = innerW / horas.length;
  const H = PAD_T + dias.length * ROW_H + (dias.length - 1) * GAP + PAD_B;

  const max = Math.max(0, ...matriz.flat());
  const xAt = (h) => PAD_L + h * COL_W;
  const yAt = (i) => PAD_T + i * (ROW_H + GAP);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }} preserveAspectRatio="none">
      <defs>
        {dias.map((dia, i) => (
          <linearGradient key={dia} id={`congDia${i}`} x1="0" y1="0" x2="1" y2="0">
            {horas.map((h) => (
              <stop key={h} offset={`${((h + 0.5) / horas.length) * 100}%`}
                style={{ stopColor: dias_con_datos[i][h] > 0 ? colorHeatSuave(matriz[i][h], max) : "var(--bg-3)" }} />
            ))}
          </linearGradient>
        ))}
        <linearGradient id="heatLegendGrad" x1="0" y1="0" x2="1" y2="0">
          {HEAT_RAMP.map((c, i) => (
            <stop key={i} offset={`${(i / (HEAT_RAMP.length - 1)) * 100}%`} stopColor={c} />
          ))}
        </linearGradient>
      </defs>
      {horas.map((h) => h % 3 === 0 && (
        <text key={h} x={xAt(h) + COL_W / 2} y={PAD_T - 9} textAnchor="middle" fontSize="15"
          fill="var(--fg-2)" fontFamily="var(--font-metric)">{h}</text>
      ))}
      {dias.map((dia, i) => (
        <g key={dia}>
          <text x={PAD_L - 8} y={yAt(i) + ROW_H / 2 + 5} textAnchor="end" fontSize="16" fontWeight="500"
            fill="var(--fg-1)" fontFamily="var(--font-ui)">{dia}</text>
          <rect x={PAD_L} y={yAt(i)} width={innerW} height={ROW_H} rx={ROW_H / 2} fill={`url(#congDia${i})`} />
          {/* Zonas sensibles al mouse: una por hora, con el detalle en el tooltip */}
          {horas.map((h) => {
            const conDatos = dias_con_datos[i][h] > 0;
            return (
              <rect key={h} className="heat-cell" x={xAt(h)} y={yAt(i)} width={COL_W} height={ROW_H} fill="transparent">
                <title>
                  {`${dia} ${String(h).padStart(2, "0")}-${String((h + 1) % 24).padStart(2, "0")}hs — `
                    + (conDatos ? `${matriz[i][h]} personas en promedio (${dias_con_datos[i][h]} día${dias_con_datos[i][h] === 1 ? "" : "s"})` : "sin datos")}
                </title>
              </rect>
            );
          })}
        </g>
      ))}
      {/* Leyenda: rampa secuencial baja -> alta */}
      <text x={PAD_L} y={H - 12} fontSize="15" fill="var(--fg-2)" fontFamily="var(--font-ui)">menos gente</text>
      <rect x={PAD_L + 100} y={H - 25} width={150} height={12} rx="6" fill="url(#heatLegendGrad)" />
      <text x={PAD_L + 262} y={H - 12} fontSize="15" fill="var(--fg-2)" fontFamily="var(--font-ui)">más gente</text>
    </svg>
  );
}

export {
  BarChart, CongestionHeatmap,
  useTendenciaSemanal, usePermanenciaSemanal, usePromedioDiario, usePosiblesEmpleados,
  useConversionCompra, usePermanenciaPorZona, useCongestionHoraria,
}
