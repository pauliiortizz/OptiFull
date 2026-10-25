import React from 'react'
import { useResortes, useResorte, useCuenta, decimalesDe } from '../efectos/graficos.js'
import '../efectos/graficos.css'

// Hooks de datos y gráficos de las métricas de reportes que muestra el Dashboard.
// Pide un reporte y devuelve { data, loading }. Si el servidor responde con
// error (ej. 500 {"error": ...} cuando la consulta falla), data queda en null
// igual que si no hubiera red: el cuerpo del error NO se usa como si fueran
// datos (antes rompia el grafico de congestion y dejaba el Dashboard en blanco).
// 'rango' ({desde, hasta}, opcional) es el filtro del dashboard y se manda como ?desde=&hasta=; 'tick' cambia
// con "Actualizar datos" y vuelve a pedir el reporte (antes se pedia una sola vez: si ese pedido fallaba, el
// panel quedaba vacio hasta recargar la pagina).
function useReporte(url, rango, tick = 0) {
  const [data, setData]       = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const conRango = rango ? `${url}?desde=${rango.desde}&hasta=${rango.hasta}` : url;
  React.useEffect(() => {
    let cancelado = false;
    setLoading(true);
    fetch(conRango)
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (!cancelado) { setData(d); setLoading(false); } })
      .catch(() => { if (!cancelado) { setData(null); setLoading(false); } });
    return () => { cancelado = true; };
  }, [conRango, tick]);
  return { data, loading };
}

// Promedio real de personas detectadas por dia de la semana (suma todos los
// videos analizados de una misma fecha calendario, y promedia esos totales
// entre todas las fechas que cayeron en cada dia de la semana).
function useTendenciaSemanal(rango, tick) {
  return useReporte('/api/reportes/tendencia-semanal', rango, tick);
}

// Permanencia real promedio (minutos) por dia de la semana (ver
// /reportes/permanencia-semanal en el backend: promedia el tiempo real de
// permanencia por cliente y dia, y luego entre todas las fechas que cayeron
// en cada dia de la semana).
function usePermanenciaSemanal(rango, tick) {
  return useReporte('/api/reportes/permanencia-semanal', rango, tick);
}

// Promedio de personas unicas detectadas por dia (sumatoria de clientes
// distintos por fecha, promediada entre los dias con datos). Por ahora solo
// camara 4; se combinara con las demas camaras a futuro.
function usePromedioDiario(rango, tick) {
  return useReporte('/api/reportes/promedio-diario', rango, tick);
}

// Promedio diario de clientes reales que COMPRARON vs. que NO compraron
// nada (ver /reportes/conversion-compra en el backend: clasificacion
// Escenario A/B/C de deteccion/pipeline/eventos.py, tabla 'eventos').
function useConversionCompra(rango, tick) {
  return useReporte('/api/reportes/conversion-compra', rango, tick);
}

// Permanencia real por zona (Caja/Gondolas/Salon) -- minutos promedio por
// visitante, estimado a partir de los puntos de trayectoria de cada zona.
function usePermanenciaPorZona(rango, tick) {
  return useReporte('/api/reportes/permanencia-por-zona', rango, tick);
}

// Horarios estimados de congestion: cuanta gente (personas unicas) hubo en
// camara por franja horaria, dia por dia de la semana (ver
// /reportes/congestion-horaria en el backend, que usa 'visitas' para no
// contar huecos y promedia entre todas las fechas de cada dia de semana).
function useCongestionHoraria(rango, tick) {
  return useReporte('/api/reportes/congestion-horaria', rango, tick);
}

// Tendencia semanal (barras de «Pulso» con el morfado de «Instrumental»):
// las barras crecen escalonadas con resorte y, al pasar de Flujo a Espera,
// morfan a la nueva serie pasándose un poco; la escala también se ajusta
// sin saltos. La barra de hoy destaca; con el cursor, la barra da su valor.
const HOY = (new Date().getDay() + 6) % 7;   // 0 = lunes, como las etiquetas

// 'destacar': indice de la barra de hoy (por defecto, el dia de la semana actual en Lun..Dom); 'pies': texto
// bajo cada barra ("sin datos" si diasConDatos es 0); 'promedio': el globo dice "en promedio".
function BarChart({ data, labels, diasConDatos, unidad = "", destacar = HOY, pies, promedio = true }) {
  const W = 640, H = 330, PAD_L = 44, PAD_R = 8, PAD_T = 26, PAD_B = 50;
  const innerW = W - PAD_L - PAD_R, innerH = H - PAD_T - PAD_B;
  const [hov, setHov] = React.useState(null);
  const meta = Math.max(1, ...data) * 1.15;
  const max = useResorte(meta, { k: 120, c: 16, desde: meta });
  const vals = useResortes(data, { k: 150, c: 17 });
  const ent = useResortes(data.map(() => 1), { k: 30, c: 10.4 });
  const dec = Math.max(...data.map(decimalesDe));
  const bw = innerW / data.length * 0.55;
  const groupW = innerW / data.length;

  const yTicks = 4;
  const ticks = Array.from({ length: yTicks + 1 }, (_, i) => Math.round((meta / yTicks) * i));
  const yAt = (v) => PAD_T + innerH - (Math.max(0, v) / max) * innerH;
  const n = data.length;
  // cada barra entra un poco después que la anterior (el escalonado de Instrumental)
  const alto = (i) => vals[i] * Math.max(0, Math.min(1, ent[i] * 1.7 - i / n * .7));

  const g = hov != null ? { x: PAD_L + groupW * hov + groupW / 2, y: yAt(alto(hov)) } : null;
  const nHov = hov != null ? diasConDatos?.[hov] : null;
  const pieDe = (i) => {
    const nd = diasConDatos ? diasConDatos[i] : null;
    if (nd === 0) return "sin datos";
    return pies ? pies[i] : null;
  };
  return (
    <div className="gr-lienzo">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}
        className={`gr-barras${hov != null ? " is-hover" : ""}`} onPointerLeave={() => setHov(null)}>
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
          const nd  = diasConDatos ? diasConDatos[i] : null;
          const sinDatos = nd === 0;
          const hoy = i === destacar;
          const pie = pieDe(i);
          const y = yAt(alto(i));
          return (
            <g key={i}>
              <text x={cx} y={H - 28} textAnchor="middle" fontSize="16" fontWeight={hoy ? 700 : 500}
                fill={hoy ? "var(--fg-0)" : "var(--fg-1)"} fontFamily="var(--font-ui)">{l}</text>
              {pie != null && (
                <text x={cx} y={H - 8} textAnchor="middle" fontSize="13"
                  fill="var(--fg-3)" fontFamily="var(--font-metric)">{pie}</text>
              )}
              <rect className={`gr-barra${hov === i ? " is-hover" : ""}`} x={cx - bw/2} y={y} width={bw} height={Math.max(0, H - PAD_B - y)}
                fill={sinDatos ? "var(--fg-3)" : hoy ? "var(--brand)" : "var(--brand-soft)"} opacity={sinDatos ? .25 : 1} rx="4" />
              {!sinDatos && (
                <text x={cx} y={y - 6} textAnchor="middle" opacity={Math.min(1, ent[i])}
                  fontSize="16" fill="var(--fg-0)" fontFamily="var(--font-metric)" fontWeight="600">
                  {Math.max(0, vals[i]).toLocaleString("es-AR", { minimumFractionDigits: dec, maximumFractionDigits: dec })}
                </text>
              )}
              <rect className="gr-zona" x={PAD_L + groupW * i} y={PAD_T} width={groupW} height={innerH}
                onPointerEnter={() => setHov(i)} />
            </g>
          );
        })}
      </svg>
      <div className={`gr-globo${g ? " is-visible" : ""}`}
        style={g ? { left: `${g.x / W * 100}%`, top: `${g.y / H * 100}%` } : undefined}>
        {hov != null && <>
          <small>
            {labels[hov]}{hov === destacar ? " · hoy" : ""}
            {nHov === 0 ? " · sin datos" : ""}
          </small>
          {data[hov].toLocaleString("es-AR", { maximumFractionDigits: dec })}{unidad && ` ${unidad}`}{promedio ? " en promedio" : ""}
        </>}
      </div>
    </div>
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

// Horario de congestión (la tira de calor de «Instrumental»): una celda por
// hora y día, del pálido (menos gente) al intenso (más gente), que entran
// escalonadas en diagonal. Con el cursor, la celda se marca, el resto baja de
// brillo y un globo da el detalle. El pico más alto late con un anillo; los
// demás picos llevan un contorno punteado. La hora y el día actuales van en negrita.
// 'destacar': fila de hoy (por defecto el día de la semana actual, en Lun..Dom). data.futuro (opcional, misma
// forma que matriz) marca las horas de hoy que todavía no pasaron.
function CongestionHeatmap({ data, destacar = HOY }) {
  const { dias, horas, matriz, dias_con_datos, picos = [], futuro } = data;
  const W = 640, PAD_L = dias.some((d) => d.length > 3) ? 62 : 42, PAD_R = 6, PAD_T = 26, PAD_B = 44;
  const ROW_H = 30, GAP = 8, CGAP = 2.4;
  const innerW = W - PAD_L - PAD_R;
  const COL_W = innerW / horas.length;
  const H = PAD_T + dias.length * ROW_H + (dias.length - 1) * GAP + PAD_B;
  const [hov, setHov] = React.useState(null);   // [fila del día, hora]
  const horaActual = new Date().getHours();

  const max = Math.max(0, ...matriz.flat());
  const xAt = (h) => PAD_L + h * COL_W;
  const yAt = (i) => PAD_T + i * (ROW_H + GAP);

  const arriba = hov && hov[0] === 0;   // en la primera fila el globo va por debajo, para no tapar las horas
  const g = hov ? { x: xAt(hov[1]) + COL_W / 2, y: arriba ? yAt(0) + ROW_H : yAt(hov[0]) } : null;
  const nHov = hov ? dias_con_datos[hov[0]][hov[1]] : 0;
  const futHov = hov ? futuro?.[hov[0]]?.[hov[1]] : false;
  return (
    <div className="gr-lienzo">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }}
        className={`gr-calor${hov ? " is-hover" : ""}`} onPointerLeave={() => setHov(null)}>
        <defs>
          <linearGradient id="heatLegendGrad" x1="0" y1="0" x2="1" y2="0">
            {HEAT_RAMP.map((c, i) => (
              <stop key={i} offset={`${(i / (HEAT_RAMP.length - 1)) * 100}%`} stopColor={c} />
            ))}
          </linearGradient>
        </defs>
        {horas.map((h) => h % 3 === 0 && (
          <text key={h} x={xAt(h) + COL_W / 2} y={PAD_T - 9} textAnchor="middle" fontSize="15"
            className={h === horaActual ? "gr-hora-actual" : undefined}
            fill="var(--fg-2)" fontFamily="var(--font-metric)">{h}</text>
        ))}
        {horaActual % 3 !== 0 && (
          <circle cx={xAt(horaActual) + COL_W / 2} cy={PAD_T - 14} r="2.6" fill="var(--fg-0)" />
        )}
        {dias.map((dia, i) => (
          <g key={dia}>
            <text x={PAD_L - 8} y={yAt(i) + ROW_H / 2 + 5} textAnchor="end" fontSize="16" fontWeight={i === destacar ? 700 : 500}
              fill={i === destacar ? "var(--fg-0)" : "var(--fg-1)"} fontFamily="var(--font-ui)">{dia}</text>
            {horas.map((h) => {
              const conDatos = dias_con_datos[i][h] > 0;
              const esFuturo = !!futuro?.[i]?.[h];
              const esHov = hov && hov[0] === i && hov[1] === h;
              return (
                <rect key={h} className={`gr-celda${esHov ? " is-hover" : ""}`}
                  x={xAt(h) + CGAP / 2} y={yAt(i)} width={COL_W - CGAP} height={ROW_H} rx="5"
                  fill={conDatos ? colorHeatSuave(matriz[i][h], max) : "var(--bg-3)"} opacity={esFuturo ? .35 : 1}
                  style={{ "--d": `${(h + i * 2) * 14 + 60}ms` }}
                  onPointerEnter={() => setHov([i, h])} />
              );
            })}
          </g>
        ))}
        {picos.map((p, k) => {
          const i = dias.indexOf(p.dia);
          if (i < 0) return null;
          return (
            <rect key={k} className={`gr-pico${k ? " es-otro" : ""}`}
              x={xAt(p.hora_inicio) - 1} y={yAt(i) - 3} rx="8"
              width={(p.hora_fin - p.hora_inicio + 1) * COL_W + 2} height={ROW_H + 6} />
          );
        })}
        {/* Leyenda: rampa secuencial baja -> alta */}
        <text x={PAD_L} y={H - 12} fontSize="15" fill="var(--fg-2)" fontFamily="var(--font-ui)">menos gente</text>
        <rect x={PAD_L + 100} y={H - 25} width={150} height={12} rx="6" fill="url(#heatLegendGrad)" />
        <text x={PAD_L + 262} y={H - 12} fontSize="15" fill="var(--fg-2)" fontFamily="var(--font-ui)">más gente</text>
      </svg>
      <div className={`gr-globo${g ? " is-visible" : ""}${arriba ? " is-abajo" : ""}`}
        style={g ? { left: `${g.x / W * 100}%`, top: `${g.y / H * 100}%` } : undefined}>
        {hov && <>
          <small>{dias[hov[0]]} {String(hov[1]).padStart(2, "0")}–{String((hov[1] + 1) % 24).padStart(2, "0")} hs</small>
          {futHov ? "todavía no pasó"
            : nHov > 0 ? `${matriz[hov[0]][hov[1]]} personas`
            : "sin datos"}
        </>}
      </div>
    </div>
  );
}

// Conversión de compra (el anillo de «Instrumental»): 60 marcas que se llenan
// con resorte hasta el porcentaje, con la cifra que cuenta en el centro, y al
// lado las dos barras de compraron / no compraron, que crecen igual.
// Sin porcentaje (ningún visitante en esos días) el anillo queda vacío con «—»: un 0 % sería un dato
// inventado (RNF-04, DEF-021).
function AnilloConversion({ pct, compraron, noCompraron }) {
  const N = 60, R = 58, C = 64;
  const sinPct = pct == null;
  const lleno = useResorte(sinPct ? 0 : Math.max(0, Math.min(100, pct)) / 100 * N, { k: 34, c: 8.6 });
  const cifra = useCuenta(sinPct ? "—" : pct, decimalesDe(pct));
  const filas = [
    { label: "Compraron", valor: compraron, color: "var(--pos-soft)" },
    { label: "No compraron", valor: noCompraron, color: "var(--fg-3)" },
  ];
  const maxF = Math.max(...filas.map(f => f.valor), 1);
  const anchos = useResortes(filas.map(f => f.valor / maxF), { k: 90, c: 14 });
  return (
    <div className="gr-conversion">
      <svg className="gr-anillo" viewBox="0 0 128 128" role="img" aria-label={sinPct ? "Conversión sin datos" : `${pct}% de conversión`}>
        {Array.from({ length: N }, (_, i) => {
          const an = -Math.PI / 2 + i / N * Math.PI * 2, mayor = i % 5 === 0, r0 = R - (mayor ? 13 : 10);
          const f = Math.max(0, Math.min(1, lleno - i));   // 1 llena, 0 vacía; entre medio, la que se está llenando
          return (
            <line key={i} x1={C + Math.cos(an) * r0} y1={C + Math.sin(an) * r0} x2={C + Math.cos(an) * R} y2={C + Math.sin(an) * R}
              stroke={f > 0 ? "var(--pos-soft)" : "var(--fg-3)"} strokeOpacity={f > 0 ? .25 + .75 * f : .22}
              strokeWidth="2.6" strokeLinecap="round" />
          );
        })}
        <text x={C} y={C + 4} textAnchor="middle" fontSize="23" fontWeight="600" fill="var(--fg-0)" fontFamily="var(--font-metric)">{sinPct ? cifra : `${cifra}%`}</text>
        <text x={C} y={C + 20} textAnchor="middle" fontSize="8.5" letterSpacing=".12em" fill="var(--fg-3)" fontFamily="var(--font-ui)">CONVERSIÓN</text>
      </svg>
      <div className="gr-filas">
        {filas.map((f, i) => (
          <div key={f.label}>
            <div className="gr-fila-cab"><b>{f.label}</b><span>{f.valor} / día</span></div>
            <div className="gr-pista"><i style={{ width: `${Math.max(0, anchos[i]) * 100}%`, background: f.color }} /></div>
          </div>
        ))}
      </div>
    </div>
  );
}

export {
  BarChart, CongestionHeatmap, AnilloConversion,
  useTendenciaSemanal, usePermanenciaSemanal, usePromedioDiario,
  useConversionCompra, usePermanenciaPorZona, useCongestionHoraria,
}
