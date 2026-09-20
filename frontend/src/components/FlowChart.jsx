import { useState } from 'react'

export function FlowChart({ today, yesterday, hours, currentHour = 18 }) {
  const W = 720, H = 240;
  const PAD_L = 36, PAD_R = 12, PAD_T = 16, PAD_B = 28;
  const innerW = W - PAD_L - PAD_R, innerH = H - PAD_T - PAD_B;

  const all = [...today, ...yesterday];
  const max = Math.ceil(Math.max(...all) / 10) * 10;
  const min = 0;

  const xAt = (i) => PAD_L + (i / (hours.length - 1)) * innerW;
  const yAt = (v) => PAD_T + innerH - ((v - min) / (max - min)) * innerH;

  const linePath = (arr, only) => {
    const sliced = only != null ? arr.slice(0, only + 1) : arr;
    return sliced.reduce((acc, v, i) => {
      const x = xAt(i), y = yAt(v);
      if (i === 0) return `M ${x} ${y}`;
      const px = xAt(i - 1), py = yAt(sliced[i - 1]);
      const cpx = (px + x) / 2;
      return `${acc} C ${cpx} ${py} ${cpx} ${y} ${x} ${y}`;
    }, "");
  };
  const areaPath = (arr, only) => {
    const p = linePath(arr, only);
    const lastIdx = only != null ? only : arr.length - 1;
    return `${p} L ${xAt(lastIdx)} ${H - PAD_B} L ${PAD_L} ${H - PAD_B} Z`;
  };

  const [hover, setHover] = useState(null);
  const yTicks = 4;
  const ticks = Array.from({ length: yTicks + 1 }, (_, i) => Math.round((max / yTicks) * i));

  const onMove = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * W;
    const idx = Math.round(((x - PAD_L) / innerW) * (hours.length - 1));
    if (idx >= 0 && idx < hours.length) setHover(idx);
    else setHover(null);
  };

  const futurePath = (() => {
    const future = today.slice(currentHour);
    return future.reduce((acc, v, i) => {
      const realI = i + currentHour;
      const x = xAt(realI), y = yAt(v);
      if (i === 0) return `M ${x} ${y}`;
      const px = xAt(realI - 1), py = yAt(today[realI - 1]);
      const cpx = (px + x) / 2;
      return `${acc} C ${cpx} ${py} ${cpx} ${y} ${x} ${y}`;
    }, "");
  })();

  return (
    <div className="flow-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block" }} preserveAspectRatio="none"
        onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        <defs>
          <linearGradient id="flow-today" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--traffic)" stopOpacity="0.14" />
            <stop offset="100%" stopColor="var(--traffic)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={PAD_L} x2={W - PAD_R} y1={yAt(t)} y2={yAt(t)}
              stroke="var(--line-soft)" strokeDasharray={i === 0 ? "0" : "2 4"} />
            <text x={PAD_L - 8} y={yAt(t) + 3} textAnchor="end" fontSize="11.5"
              fill="var(--fg-3)" fontFamily="var(--font-metric)">{t}</text>
          </g>
        ))}

        {hours.map((h, i) => (
          (i % 3 === 0 || i === hours.length - 1) && (
            <text key={i} x={xAt(i)} y={H - 10} textAnchor="middle" fontSize="11.5"
              fill="var(--fg-3)" fontFamily="var(--font-metric)">{h}</text>
          )
        ))}

        <path d={linePath(yesterday)} stroke="var(--fg-3)" strokeWidth="1.4" fill="none"
          strokeDasharray="3 3" opacity=".75" />

        <path d={areaPath(today, currentHour)} fill="url(#flow-today)" />
        <path d={linePath(today, currentHour)} stroke="var(--traffic)" strokeWidth="2"
          fill="none" strokeLinecap="round" />

        <path d={futurePath} stroke="var(--traffic)" strokeWidth="1.4" fill="none"
          strokeDasharray="4 4" opacity=".4" />

        <line x1={xAt(currentHour)} x2={xAt(currentHour)} y1={PAD_T} y2={H - PAD_B}
          stroke="var(--traffic)" strokeWidth="1" opacity=".5" strokeDasharray="2 3" />
        <circle cx={xAt(currentHour)} cy={yAt(today[currentHour])} r="4" fill="var(--bg-2)"
          stroke="var(--traffic)" strokeWidth="2" />
        <circle cx={xAt(currentHour)} cy={yAt(today[currentHour])} r="8" fill="var(--traffic)" opacity=".12">
          <animate attributeName="r" values="4;10;4" dur="2s" repeatCount="indefinite" />
          <animate attributeName="opacity" values=".3;0;.3" dur="2s" repeatCount="indefinite" />
        </circle>

        {hover != null && (
          <g>
            <line x1={xAt(hover)} x2={xAt(hover)} y1={PAD_T} y2={H - PAD_B}
              stroke="var(--fg-2)" strokeWidth="1" opacity=".4" />
            <circle cx={xAt(hover)} cy={yAt(today[hover])} r="3.5" fill="var(--traffic)" />
            <circle cx={xAt(hover)} cy={yAt(yesterday[hover])} r="3" fill="var(--fg-3)" />
            <g transform={`translate(${Math.min(xAt(hover) + 8, W - 110)}, ${PAD_T + 4})`}>
              <rect width="100" height="50" rx="3" fill="var(--bg-2)" stroke="var(--line)" />
              <text x="8" y="14" fontSize="11.5" fill="var(--fg-3)" fontFamily="var(--font-metric)">{hours[hover]}</text>
              <text x="8" y="28" fontSize="12.5" fill="var(--traffic)" fontFamily="var(--font-metric)">
                <tspan fontWeight="600">{today[hover]}</tspan>
                <tspan fill="var(--fg-3)" fontSize="11"> hoy</tspan>
              </text>
              <text x="8" y="42" fontSize="12.5" fill="var(--fg-2)" fontFamily="var(--font-metric)">
                <tspan fontWeight="600">{yesterday[hover]}</tspan>
                <tspan fill="var(--fg-3)" fontSize="11"> ayer</tspan>
              </text>
            </g>
          </g>
        )}
      </svg>
    </div>
  );
}
