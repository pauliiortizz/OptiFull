// Iconos de la app: una sola familia, Phosphor (@phosphor-icons/react, licencia MIT), todos con el mismo peso.
// Antes convivian iconos de relleno descargados (frontend/icons/*.svg) y otros de trazo dibujados a mano, con
// proporciones y grosores distintos. Cada IcoAlgo conserva su nombre y sus props (size, style, className), asi
// que las paginas no cambian; para cambiar un icono basta elegir otro de https://phosphoricons.com.
// Import de a un icono por archivo: el indice del paquete trae los ~1500 iconos y hacia lentos el servidor de
// desarrollo y los tests (en el build da igual, Vite descarta los que no se usan).
import { ArrowsClockwise } from '@phosphor-icons/react/dist/csr/ArrowsClockwise';
import { Bell } from '@phosphor-icons/react/dist/csr/Bell';
import { BookOpen } from '@phosphor-icons/react/dist/csr/BookOpen';
import { CalendarBlank } from '@phosphor-icons/react/dist/csr/CalendarBlank';
import { CaretDown } from '@phosphor-icons/react/dist/csr/CaretDown';
import { CaretRight } from '@phosphor-icons/react/dist/csr/CaretRight';
import { ChartBar } from '@phosphor-icons/react/dist/csr/ChartBar';
import { Check } from '@phosphor-icons/react/dist/csr/Check';
import { Clock } from '@phosphor-icons/react/dist/csr/Clock';
import { Code } from '@phosphor-icons/react/dist/csr/Code';
import { Copy } from '@phosphor-icons/react/dist/csr/Copy';
import { CornersOut } from '@phosphor-icons/react/dist/csr/CornersOut';
import { Cpu } from '@phosphor-icons/react/dist/csr/Cpu';
import { DotsThree } from '@phosphor-icons/react/dist/csr/DotsThree';
import { DownloadSimple } from '@phosphor-icons/react/dist/csr/DownloadSimple';
import { Eye } from '@phosphor-icons/react/dist/csr/Eye';
import { FastForward } from '@phosphor-icons/react/dist/csr/FastForward';
import { FileText } from '@phosphor-icons/react/dist/csr/FileText';
import { Funnel } from '@phosphor-icons/react/dist/csr/Funnel';
import { GearSix } from '@phosphor-icons/react/dist/csr/GearSix';
import { House } from '@phosphor-icons/react/dist/csr/House';
import { MagnifyingGlass } from '@phosphor-icons/react/dist/csr/MagnifyingGlass';
import { MapTrifold } from '@phosphor-icons/react/dist/csr/MapTrifold';
import { MinusSquare } from '@phosphor-icons/react/dist/csr/MinusSquare';
import { Moon } from '@phosphor-icons/react/dist/csr/Moon';
import { Package } from '@phosphor-icons/react/dist/csr/Package';
import { PaperPlaneRight } from '@phosphor-icons/react/dist/csr/PaperPlaneRight';
import { Path } from '@phosphor-icons/react/dist/csr/Path';
import { Pause } from '@phosphor-icons/react/dist/csr/Pause';
import { Play } from '@phosphor-icons/react/dist/csr/Play';
import { Receipt } from '@phosphor-icons/react/dist/csr/Receipt';
import { Rewind } from '@phosphor-icons/react/dist/csr/Rewind';
import { SignOut } from '@phosphor-icons/react/dist/csr/SignOut';
import { Sparkle } from '@phosphor-icons/react/dist/csr/Sparkle';
import { SquaresFour } from '@phosphor-icons/react/dist/csr/SquaresFour';
import { Sun } from '@phosphor-icons/react/dist/csr/Sun';
import { TrendUp } from '@phosphor-icons/react/dist/csr/TrendUp';
import { UploadSimple } from '@phosphor-icons/react/dist/csr/UploadSimple';
import { User } from '@phosphor-icons/react/dist/csr/User';
import { Users } from '@phosphor-icons/react/dist/csr/Users';
import { VideoCamera } from '@phosphor-icons/react/dist/csr/VideoCamera';
import { Warehouse } from '@phosphor-icons/react/dist/csr/Warehouse';
import { WarningCircle } from '@phosphor-icons/react/dist/csr/WarningCircle';
import { X } from '@phosphor-icons/react/dist/csr/X';

// Peso unico de toda la app ('thin' | 'light' | 'regular' | 'bold'). stroke >= 2 (usado en algun boton
// destacado) pide la version 'bold'.
const PESO = 'regular';

const icono = (Componente) => function Ico({ size = 16, stroke, weight, ...rest }) {
  return <Componente size={size} weight={weight ?? (stroke >= 2 ? 'bold' : PESO)} {...rest} />;
};

export const IcoDashboard = icono(SquaresFour);
export const IcoHome      = icono(House);
export const IcoHeat      = icono(MapTrifold);
export const IcoTrack     = icono(Path);
export const IcoStock     = icono(Warehouse);
export const IcoReport    = icono(ChartBar);
export const IcoAlert     = icono(WarningCircle);
export const IcoSettings  = icono(GearSix);
export const IcoCam       = icono(VideoCamera);
export const IcoUsers     = icono(Users);
export const IcoClock     = icono(Clock);
export const IcoSun       = icono(Sun);
export const IcoMoon      = icono(Moon);
export const IcoBell      = icono(Bell);
export const IcoBox       = icono(Package);
export const IcoReceipt   = icono(Receipt);
export const IcoTrend     = icono(TrendUp);
export const IcoChev      = icono(CaretRight);
export const IcoSearch    = icono(MagnifyingGlass);
export const IcoMore      = icono(DotsThree);
export const IcoExpand    = icono(CornersOut);
export const IcoDown      = icono(CaretDown);
export const IcoExit      = icono(SignOut);
export const IcoEye       = icono(Eye);
export const IcoDocs      = icono(FileText);
export const IcoCheck     = icono(Check);
export const IcoSpinner   = icono(ArrowsClockwise);
export const IcoTodo      = icono(MinusSquare);
export const IcoCopy      = icono(Copy);
export const IcoSparkle   = icono(Sparkle);
export const IcoFilter    = icono(Funnel);
export const IcoDownload  = icono(DownloadSimple);
export const IcoCalendar  = icono(CalendarBlank);
export const IcoX         = icono(X);
export const IcoSend      = icono(PaperPlaneRight);
export const IcoPlay      = icono(Play);
export const IcoCode      = icono(Code);
export const IcoBook      = icono(BookOpen);
export const IcoChip      = icono(Cpu);
export const IcoUser      = icono(User);
export const IcoCheck2    = icono(Check);
export const IcoUpload    = icono(UploadSimple);
export const IcoPause     = icono(Pause);
export const IcoRewind    = icono(Rewind);
export const IcoForward   = icono(FastForward);
