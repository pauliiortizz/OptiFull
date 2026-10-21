import '../efectos/vista-mail.css'

/* =====================================================================
   Vista del mail — al lado del formulario «Probalo en tu tienda».
   Una ventana de «Mensaje nuevo», como la de redactar de un webmail, que
   escribe en vivo el aviso que le llega a OptiFull (la misma plantilla de
   frontend/api/correo.py): Para, Asunto y el cuerpo con cada dato. Las
   letras suben a su sitio a medida que se escriben (el relieve de
   «Reverso · Moxen») y el cursor parpadea en el dato del campo con foco.
   Al enviarse, «Enviar» pasa a «Enviando…», la ventana se va hacia abajo
   y queda el aviso de «Mensaje enviado».
   Es decorativa (aria-hidden): el formulario de verdad es el de al lado.
   ===================================================================== */

const DESTINO = 'optifull27@gmail.com';

// [clave, etiqueta en el mail], en el orden de la plantilla
const LINEAS = [
  ['nombre', 'Nombre y Apellido'],
  ['rol', 'Rol / Cargo'],
  ['estacion', 'Estación y Localidad'],
  ['camaras', 'Cantidad de Cámaras'],
  ['problema', 'Prioridad a resolver'],
  ['contacto', 'WhatsApp / Email de contacto'],
];
const ENTEROS = { rol: 1, camaras: 1, problema: 1 };   // vienen de un selector: entran completos

/* Un dato que se escribe: cada letra nueva sube a su sitio con un rebote;
   los que vienen de un selector entran completos, letra por letra. */
function Escrito({ texto, entero }) {
  const t = (texto || '').trim();
  if (!t) return null;
  return (
    <span className="vm-escrito" key={entero ? t : undefined}>
      {[...t].map((ch, i) => (
        <i key={i} style={entero ? { animationDelay: `${i * 12}ms` } : undefined}>{ch === ' ' ? ' ' : ch}</i>
      ))}
    </span>
  );
}

const Ico = ({ d, ...p }) => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...p}><path d={d} /></svg>
);
// íconos de la barra (trazos genéricos)
const I = {
  undo: 'M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11',
  redo: 'm15 14 5-5-5-5M20 9H9.5a5.5 5.5 0 0 0 0 11H13',
  negrita: 'M7 5h6a3.5 3.5 0 0 1 0 7H7zM7 12h7a3.5 3.5 0 0 1 0 7H7z',
  cursiva: 'M10 5h8M6 19h8M14 5l-4 14',
  subrayado: 'M7 4v7a5 5 0 0 0 10 0V4M5 20h14',
  alinear: 'M4 6h16M4 10h10M4 14h16M4 18h10',
  lista: 'M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01',
  clip: 'm21 11-8.6 8.6a5 5 0 0 1-7-7L14 4a3.3 3.3 0 0 1 4.7 4.7l-8.5 8.5a1.7 1.7 0 0 1-2.4-2.4L15.6 7',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
  emoji: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8.5 14.5a4.5 4.5 0 0 0 7 0M9 9.5h.01M15 9.5h.01',
  imagen: 'M4 5h16v14H4zM4 16l5-5 4 4 2-2 5 5M15 9.5h.01',
  mas: 'M12 5h.01M12 12h.01M12 19h.01',
  basura: 'M5 7h14M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  flecha: 'm7 10 5 5 5-5',
};

export function VistaMail({ valores = {}, zona = null, enviando = false, listo = false }) {
  const v = (k) => (valores[k] || '').trim();
  const asunto = v('nombre') || v('estacion')
    ? `Nueva solicitud de demo — ${v('nombre') || '…'} (${v('estacion') || '…'})`
    : '';
  const cursor = (k) => zona === k && !listo && <span className="vm-cursor" />;

  return (
    <div className={`vm${listo ? ' is-enviado' : ''}`} aria-hidden="true">
      <div className="vm-ventana">
        <div className="vm-barra">
          <span>Mensaje nuevo</span>
          <span className="vm-controles"><i className="vm-min" /><i className="vm-max" /><i className="vm-cerrar" /></span>
        </div>

        <div className="vm-campo"><span className="vm-rotulo">Para</span><span className="vm-chip">{DESTINO}</span><span className="vm-cc">Cc Cco</span></div>
        <div className="vm-campo">
          {asunto ? <Escrito texto={asunto} /> : <span className="vm-rotulo">Asunto</span>}
        </div>

        <div className="vm-cuerpo">
          <p className="vm-regla" />
          <p className="vm-titulo">📩 NUEVA SOLICITUD DE DEMO - OPTIFULL</p>
          {LINEAS.map(([k, etiqueta]) => (
            <p key={k} className={`vm-linea${zona === k && !listo ? ' is-activa' : ''}`}>
              • <b>{etiqueta}:</b>{' '}
              {v(k) ? <Escrito texto={valores[k]} entero={!!ENTEROS[k]} /> : <span className="vm-falta">…</span>}
              {cursor(k)}
            </p>
          ))}
          <p className="vm-regla" />
        </div>

        <div className="vm-formato">
          <Ico d={I.undo} /><Ico d={I.redo} /><i className="vm-sep" />
          <span className="vm-fuente">Sans Serif<Ico d={I.flecha} /></span><i className="vm-sep" />
          <Ico d={I.negrita} /><Ico d={I.cursiva} /><Ico d={I.subrayado} /><i className="vm-sep" />
          <Ico d={I.alinear} /><Ico d={I.lista} />
        </div>

        <div className="vm-pie">
          <span className={`vm-enviar${enviando || listo ? ' is-pulsado' : ''}`}>
            <span>{enviando || listo ? 'Enviando…' : 'Enviar'}</span><span className="vm-enviar-mas"><Ico d={I.flecha} /></span>
          </span>
          <span className="vm-aa">Aa</span>
          <Ico d={I.clip} /><Ico d={I.link} /><Ico d={I.emoji} /><Ico d={I.imagen} />
          <span className="vm-espacio" />
          <Ico d={I.mas} /><Ico d={I.basura} />
        </div>
      </div>

      <div className="vm-aviso">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.6 4.6L19 7.5" /></svg>
        <span>Mensaje enviado a {DESTINO}</span>
      </div>
    </div>
  );
}
