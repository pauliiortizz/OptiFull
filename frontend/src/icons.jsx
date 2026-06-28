// Simple stroke-icon set — 16px viewBox, 1.5 stroke, currentColor
const Ico = ({ children, size = 16, stroke = 1.6, ...rest }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none"
    stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" {...rest}>
    {children}
  </svg>
);

const IcoDashboard = (p) => <Ico {...p}><rect x="2" y="2" width="5.5" height="6.5" rx="1.2"/><rect x="8.5" y="2" width="5.5" height="3.5" rx="1.2"/><rect x="2" y="9.5" width="5.5" height="4.5" rx="1.2"/><rect x="8.5" y="6.5" width="5.5" height="7.5" rx="1.2"/></Ico>;
const IcoHeat = (p) => <Ico {...p}><path d="M3 13c0-3 2-3 2-6S3 4 3 2"/><path d="M8 13c0-3 2-3 2-6S8 4 8 2"/><path d="M13 13c0-3-1-3-1-5"/></Ico>;
const IcoTrack = (p) => <Ico {...p}><circle cx="4" cy="4" r="1.5"/><circle cx="12" cy="12" r="1.5"/><path d="M5 5c2 0 3 2 3 4s1 3 3 3"/></Ico>;
const IcoStock = (p) => <Ico {...p}><rect x="2.5" y="3" width="11" height="10" rx="1.2"/><path d="M2.5 6.5h11M6 3v3M10 3v3"/></Ico>;
const IcoReport = (p) => <Ico {...p}><path d="M3 13.5V3a1 1 0 0 1 1-1h6.5L13 4.5v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"/><path d="M10 2.5V5h2.5M5.5 8.5h5M5.5 11h3"/></Ico>;
const IcoAlert = (p) => <Ico {...p}><path d="M8 2 1.5 13.5h13L8 2Z"/><path d="M8 6.5v3M8 11.5v.5"/></Ico>;
const IcoSettings = (p) => <Ico {...p}><circle cx="8" cy="8" r="2"/><path d="M8 1.5v1.6M8 12.9v1.6M2 8H.5M15.5 8H14M3.5 3.5l1.1 1.1M11.4 11.4l1.1 1.1M3.5 12.5l1.1-1.1M11.4 4.6l1.1-1.1"/></Ico>;
const IcoCam = (p) => <Ico {...p}><rect x="1.5" y="4" width="9" height="8" rx="1.2"/><path d="m10.5 7.5 4-2v5l-4-2v-1Z"/></Ico>;

const IcoUsers = (p) => <Ico {...p}><circle cx="6" cy="5.5" r="2.2"/><path d="M2 13c0-2.2 1.8-4 4-4s4 1.8 4 4"/><path d="M10 6a2 2 0 1 0 0-3.5M14 12.5c0-1.6-1.2-3-3-3.4"/></Ico>;
const IcoClock = (p) => <Ico {...p}><circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2 1.5"/></Ico>;
const IcoBell = (p) => <Ico {...p}><path d="M4 11c0-3 0-7 4-7s4 4 4 7"/><path d="M2.5 11h11M7 13c.3.6 1.7.6 2 0"/></Ico>;
const IcoBox = (p) => <Ico {...p}><path d="M2.5 4.5 8 2l5.5 2.5L8 7 2.5 4.5Z"/><path d="M2.5 4.5V11L8 13.5l5.5-2.5V4.5M8 7v6.5"/></Ico>;
const IcoTrend = (p) => <Ico {...p}><path d="m2 11 4-4 3 3 5-5"/><path d="M10 5h4v4"/></Ico>;
const IcoChev = (p) => <Ico {...p}><path d="m6 4 4 4-4 4"/></Ico>;
const IcoSearch = (p) => <Ico {...p}><circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3 3"/></Ico>;
const IcoMore = (p) => <Ico {...p}><circle cx="3" cy="8" r=".7"/><circle cx="8" cy="8" r=".7"/><circle cx="13" cy="8" r=".7"/></Ico>;
const IcoExpand = (p) => <Ico {...p}><path d="M2 6V2.5h3.5M14 6V2.5h-3.5M2 10v3.5h3.5M14 10v3.5h-3.5"/></Ico>;
const IcoDown = (p) => <Ico {...p}><path d="M4 6.5 8 10.5 12 6.5"/></Ico>;
const IcoExit = (p) => <Ico {...p}><path d="M7 2.5H3.5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1H7"/><path d="M10 5 13.5 8 10 11M6 8h7.5"/></Ico>;
const IcoEye = (p) => <Ico {...p}><path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8Z"/><circle cx="8" cy="8" r="2"/></Ico>;
const IcoDocs = (p) => <Ico {...p}><path d="M3.5 2h6L13 5.5v8a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z"/><path d="M9 2.5V5h3.5M5.5 8h5M5.5 10.5h5M5.5 13h3"/></Ico>;
const IcoCheck = (p) => <Ico {...p}><path d="m3 8.5 3 3 7-7.5"/></Ico>;
const IcoSpinner = (p) => <Ico {...p}><path d="M8 1.5v3M8 11.5v3M14.5 8h-3M4.5 8h-3M12.6 3.4l-2.1 2.1M5.5 10.5l-2.1 2.1M12.6 12.6l-2.1-2.1M5.5 5.5 3.4 3.4"/></Ico>;
const IcoTodo = (p) => <Ico {...p}><rect x="2.5" y="2.5" width="11" height="11" rx="2"/><path d="M5.5 8h5"/></Ico>;
const IcoCopy = (p) => <Ico {...p}><rect x="5" y="5" width="8" height="8" rx="1.5"/><path d="M3 11V4a1 1 0 0 1 1-1h7"/></Ico>;
const IcoSparkle = (p) => <Ico {...p}><path d="M8 2v3M8 11v3M2 8h3M11 8h3M4.5 4.5l2 2M9.5 9.5l2 2M4.5 11.5l2-2M9.5 6.5l2-2"/></Ico>;
const IcoFilter = (p) => <Ico {...p}><path d="M2 3.5h12L9.5 9V13l-3 1V9L2 3.5Z"/></Ico>;
const IcoDownload = (p) => <Ico {...p}><path d="M8 2v8M4.5 7 8 10.5 11.5 7M2.5 13h11"/></Ico>;
const IcoCalendar = (p) => <Ico {...p}><rect x="2.5" y="3.5" width="11" height="10" rx="1.2"/><path d="M2.5 6.5h11M5.5 2v3M10.5 2v3"/></Ico>;
const IcoX = (p) => <Ico {...p}><path d="m4 4 8 8M12 4l-8 8"/></Ico>;
const IcoSend = (p) => <Ico {...p}><path d="m2.5 8 11-5.5L9 13.5l-2-5-4.5-.5Z"/></Ico>;
const IcoPlay = (p) => <Ico {...p}><path d="m4 3 9 5-9 5V3Z"/></Ico>;
const IcoCode = (p) => <Ico {...p}><path d="m5 5-3 3 3 3M11 5l3 3-3 3M9.5 3l-3 10"/></Ico>;
const IcoBook = (p) => <Ico {...p}><path d="M3 2.5h5a2 2 0 0 1 2 2v9a1.5 1.5 0 0 0-1.5-1.5H3v-9.5Z"/><path d="M13 2.5H8a2 2 0 0 0-2 2v9a1.5 1.5 0 0 1 1.5-1.5H13v-9.5Z"/></Ico>;
const IcoChip = (p) => <Ico {...p}><rect x="4" y="4" width="8" height="8" rx="1.2"/><rect x="6" y="6" width="4" height="4"/><path d="M6 4V2M10 4V2M6 14v-2M10 14v-2M4 6H2M4 10H2M14 6h-2M14 10h-2"/></Ico>;
const IcoUser = (p) => <Ico {...p}><circle cx="8" cy="5.5" r="2.5"/><path d="M3 13.5c0-2.5 2.2-4.5 5-4.5s5 2 5 4.5"/></Ico>;
const IcoCheck2 = (p) => <Ico {...p}><circle cx="8" cy="8" r="6"/><path d="m5.5 8 1.8 1.8L10.5 6.5"/></Ico>;
const IcoUpload = (p) => <Ico {...p}><path d="M8 13.5V5.5M4.5 8.5 8 5l3.5 3.5M2.5 2.5h11"/></Ico>;

Object.assign(window, {
  Ico, IcoDashboard, IcoHeat, IcoTrack, IcoStock, IcoReport, IcoAlert, IcoSettings, IcoCam,
  IcoUsers, IcoClock, IcoBell, IcoBox, IcoTrend, IcoChev, IcoSearch, IcoMore, IcoExpand, IcoDown, IcoExit, IcoEye,
  IcoDocs, IcoCheck, IcoSpinner, IcoTodo, IcoCopy, IcoSparkle, IcoFilter, IcoDownload,
  IcoCalendar, IcoX, IcoSend, IcoPlay, IcoCode, IcoBook, IcoChip, IcoUser, IcoCheck2, IcoUpload
});
