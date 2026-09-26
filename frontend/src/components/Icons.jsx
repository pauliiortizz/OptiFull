// Iconos propios de frontend/icons/*.svg (relleno, viewBox 24). Se importan como texto y se
// renderizan siempre en negro (NEGRO), sin heredar el color del contexto como hacen los iconos de trazo.
// Para cambiar uno, basta reemplazar el archivo .svg de esa carpeta.
import actualizarSvg from '../../icons/actualizar.svg?raw';
import almacenSvg from '../../icons/almacen-alternativo.svg?raw';
import analisisSvg from '../../icons/analisis-de-macrodatos.svg?raw';
import casaSvg from '../../icons/casa-en-blanco.svg?raw';
import controlarSvg from '../../icons/controlar.svg?raw';
import descargarSvg from '../../icons/descargar.svg?raw';
import exclamacionSvg from '../../icons/exclamacion.svg?raw';
import personasSvg from '../../icons/grupo-de-personas.svg?raw';
import mapaSvg from '../../icons/mapa.svg?raw';
import rutaSvg from '../../icons/progreso-de-la-flecha.svg?raw';

// Los .svg traen margen interno en su caja de 24, asi que a igual tamano se ven mas chicos que los iconos
// de trazo: se agrandan todos por este factor (tambien los tamanos fijados via style/size en cada uso).
const ESCALA = 1.25;
const NEGRO = '#000';

const desdeSvg = (raw) => {
  const viewBox = /viewBox="([^"]+)"/.exec(raw)?.[1] ?? '0 0 24 24';
  const interior = (/<svg[^>]*>([\s\S]*)<\/svg>/.exec(raw)?.[1] ?? '').replace(/<!--[\s\S]*?-->/g, '').trim();
  return function IcoSvg({ size = 16, stroke: _stroke, style, ...rest }) {
    const escalar = (v) => (typeof v === 'number' ? v * ESCALA : v);
    const estilo = style && { ...style, width: escalar(style.width), height: escalar(style.height) };
    if (estilo && estilo.width === undefined) delete estilo.width;
    if (estilo && estilo.height === undefined) delete estilo.height;
    return <svg width={size * ESCALA} height={size * ESCALA} viewBox={viewBox} fill={NEGRO} style={estilo} {...rest}
      dangerouslySetInnerHTML={{ __html: interior }} />;
  };
};

const Ico = ({ children, size = 16, stroke = 1.6, ...rest }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none"
    stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" {...rest}>
    {children}
  </svg>
);

export const IcoDashboard = (p) => <Ico {...p}><rect x="2" y="2" width="5.5" height="6.5" rx="1.2"/><rect x="8.5" y="2" width="5.5" height="3.5" rx="1.2"/><rect x="2" y="9.5" width="5.5" height="4.5" rx="1.2"/><rect x="8.5" y="6.5" width="5.5" height="7.5" rx="1.2"/></Ico>;
export const IcoHome = desdeSvg(casaSvg);
export const IcoHeat = desdeSvg(mapaSvg);
export const IcoTrack = desdeSvg(rutaSvg);
export const IcoStock = desdeSvg(almacenSvg);
export const IcoReport = desdeSvg(analisisSvg);
export const IcoAlert = desdeSvg(exclamacionSvg);
export const IcoSettings  = (p) => <Ico {...p}><circle cx="8" cy="8" r="2"/><path d="M8 1.5v1.6M8 12.9v1.6M2 8H.5M15.5 8H14M3.5 3.5l1.1 1.1M11.4 11.4l1.1 1.1M3.5 12.5l1.1-1.1M11.4 4.6l1.1-1.1"/></Ico>;
export const IcoCam       = (p) => <Ico {...p}><rect x="1.5" y="4" width="9" height="8" rx="1.2"/><path d="m10.5 7.5 4-2v5l-4-2v-1Z"/></Ico>;
export const IcoUsers = desdeSvg(personasSvg);
export const IcoClock     = (p) => <Ico {...p}><circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2 1.5"/></Ico>;
export const IcoBell      = (p) => <Ico {...p}><path d="M4 11c0-3 0-7 4-7s4 4 4 7"/><path d="M2.5 11h11M7 13c.3.6 1.7.6 2 0"/></Ico>;
export const IcoBox = desdeSvg(almacenSvg);
export const IcoTrend     = (p) => <Ico {...p}><path d="m2 11 4-4 3 3 5-5"/><path d="M10 5h4v4"/></Ico>;
export const IcoChev      = (p) => <Ico {...p}><path d="m6 4 4 4-4 4"/></Ico>;
export const IcoSearch    = (p) => <Ico {...p}><circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/></Ico>;
export const IcoMore      = (p) => <Ico {...p}><circle cx="3" cy="8" r=".7"/><circle cx="8" cy="8" r=".7"/><circle cx="13" cy="8" r=".7"/></Ico>;
export const IcoExpand    = (p) => <Ico {...p}><path d="M2 6V2.5h3.5M14 6V2.5h-3.5M2 10v3.5h3.5M14 10v3.5h-3.5"/></Ico>;
export const IcoDown      = (p) => <Ico {...p}><path d="M4 6.5 8 10.5 12 6.5"/></Ico>;
export const IcoExit      = (p) => <Ico {...p}><path d="M7 2.5H3.5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1H7"/><path d="M10 5 13.5 8 10 11M6 8h7.5"/></Ico>;
export const IcoEye       = (p) => <Ico {...p}><path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8Z"/><circle cx="8" cy="8" r="2"/></Ico>;
export const IcoDocs = desdeSvg(analisisSvg);
export const IcoCheck = desdeSvg(controlarSvg);
export const IcoSpinner = desdeSvg(actualizarSvg);
export const IcoTodo      = (p) => <Ico {...p}><rect x="2.5" y="2.5" width="11" height="11" rx="2"/><path d="M5.5 8h5"/></Ico>;
export const IcoCopy      = (p) => <Ico {...p}><rect x="5" y="5" width="8" height="8" rx="1.5"/><path d="M3 11V4a1 1 0 0 1 1-1h7"/></Ico>;
export const IcoSparkle   = (p) => <Ico {...p}><path d="M8 2v3M8 11v3M2 8h3M11 8h3M4.5 4.5l2 2M9.5 9.5l2 2M4.5 11.5l2-2M9.5 6.5l2-2"/></Ico>;
export const IcoFilter    = (p) => <Ico {...p}><path d="M2 3.5h12L9.5 9V13l-3 1V9L2 3.5Z"/></Ico>;
export const IcoDownload = desdeSvg(descargarSvg);
export const IcoCalendar  = (p) => <Ico {...p}><rect x="2.5" y="3.5" width="11" height="10" rx="1.2"/><path d="M2.5 6.5h11M5.5 2v3M10.5 2v3"/></Ico>;
export const IcoX         = (p) => <Ico {...p}><path d="m4 4 8 8M12 4l-8 8"/></Ico>;
export const IcoSend      = (p) => <Ico {...p}><path d="m2.5 8 11-5.5L9 13.5l-2-5-4.5-.5Z"/></Ico>;
export const IcoPlay      = (p) => <Ico {...p}><path d="m4 3 9 5-9 5V3Z"/></Ico>;
export const IcoCode      = (p) => <Ico {...p}><path d="m5 5-3 3 3 3M11 5l3 3-3 3M9.5 3l-3 10"/></Ico>;
export const IcoBook      = (p) => <Ico {...p}><path d="M3 2.5h5a2 2 0 0 1 2 2v9a1.5 1.5 0 0 0-1.5-1.5H3v-9.5Z"/><path d="M13 2.5H8a2 2 0 0 0-2 2v9a1.5 1.5 0 0 1 1.5-1.5H13v-9.5Z"/></Ico>;
export const IcoChip      = (p) => <Ico {...p}><rect x="4" y="4" width="8" height="8" rx="1.2"/><rect x="6" y="6" width="4" height="4"/><path d="M6 4V2M10 4V2M6 14v-2M10 14v-2M4 6H2M4 10H2M14 6h-2M14 10h-2"/></Ico>;
export const IcoUser      = (p) => <Ico {...p}><circle cx="8" cy="5.5" r="2.5"/><path d="M3 13.5c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5"/></Ico>;
export const IcoCheck2 = desdeSvg(controlarSvg);
export const IcoUpload    = (p) => <Ico {...p}><path d="M8 13.5V5.5M4.5 8.5 8 5l3.5 3.5M2.5 2.5h11"/></Ico>;
export const IcoPause     = (p) => <Ico {...p}><rect x="3.5" y="3" width="3" height="10" rx="0.8"/><rect x="9.5" y="3" width="3" height="10" rx="0.8"/></Ico>;
export const IcoRewind    = (p) => <Ico {...p}><path d="m9 4-4 4 4 4"/><path d="m14 4-4 4 4 4"/></Ico>;
export const IcoForward   = (p) => <Ico {...p}><path d="m7 4 4 4-4 4"/><path d="m2 4 4 4-4 4"/></Ico>;
