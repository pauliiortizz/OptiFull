import { useLayoutEffect, useRef, useState } from 'react'

// Control segmentado con indicador deslizante -- una sola capa que mide la
// posición real del botón activo (getBoundingClientRect) y se traslada ahí,
// en vez de que cada botón prenda su propio fondo de golpe. Mismo mecanismo
// que ya usan el Sidebar y ReportsV2Page; centralizado acá para que el resto
// de las páginas (Heatmap, Alertas, Stock, Cámaras) no reimplementen el
// medidor. options: [[valor, etiqueta], ...].
export function GlassSeg({ options, value, onChange, ariaLabel }) {
  const wrapRef  = useRef(null);
  const itemRefs = useRef({});
  const [pill, setPill] = useState(null);

  useLayoutEffect(() => {
    const wrap = wrapRef.current;
    const el   = itemRefs.current[value];
    if (!wrap || !el) { setPill(null); return; }
    const wrapRect = wrap.getBoundingClientRect();
    const elRect   = el.getBoundingClientRect();
    setPill({ left: elRect.left - wrapRect.left, width: elRect.width });
  }, [value, options]);

  return (
    <div className="glass-seg" ref={wrapRef} role="group" aria-label={ariaLabel}>
      {pill && (
        <span className="glass-seg-pill" aria-hidden="true"
          style={{ transform: `translateX(${pill.left}px)`, width: pill.width }} />
      )}
      {options.map(([k, l]) => (
        <button key={k} type="button" ref={(el) => { itemRefs.current[k] = el; }}
          className={value === k ? 'on' : ''} aria-pressed={value === k}
          onClick={() => onChange(k)}>{l}</button>
      ))}
    </div>
  );
}
