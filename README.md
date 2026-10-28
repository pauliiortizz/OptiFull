# OptiFull - Trabajo Final 
## SISTEMA INTELIGENTE DE ANÁLISIS DE FLUJO Y OPTIMIZACIÓN OPERATIVA MEDIANTE COMPUTER VISION PARA TIENDAS FULL, OPTIFULL



- Blasón, Agostina
- Nahmias, Arnon Daniel
- Ortiz Noseda, Paulina

---

## Cómo está armado

| Carpeta | Qué es |
| --- | --- |
| `frontend/` | Panel web (React + Vite) y su API (Flask, en `frontend/api/`). |
| `deteccion/` | Análisis de las cámaras en vivo (YOLO + seguimiento de personas + mapas de calor). Corre en la computadora del local. |
| `deteccion_productos/` | Caja con detección de productos (la arranca el panel, sección Productos). |
| `db/` | Esquema de la base de datos (`schema.sql`) y scripts. |
| `test/` | Pruebas automáticas del backend. |

El panel (frontend) le pide los datos al backend (`/api/...`), y el backend los lee de la base de datos (Supabase). El programa de análisis de cámaras escribe en esa misma base.

## Requisitos

- Python 3.12 o superior
- Node.js 22
- (opcional) `ffmpeg` en el PATH, para los clips de evidencia de las alertas

## Variables de entorno (`.env`)

Creá un archivo `.env` en la raíz del repo (no se sube a git). Variables que usa el proyecto:

| Variable | Para qué |
| --- | --- |
| `DATABASE_URL` | Base de datos Postgres (Supabase). Es obligatoria. |
| `SECRET_KEY` | Firma la cookie de sesión del login. Cualquier texto largo y al azar (por ejemplo, la salida de `python -c "import secrets; print(secrets.token_hex(32))"`). Sin ella, las sesiones se pierden cada vez que se reinicia el servidor. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Guardar imágenes (mapas de calor, fotos y evidencias de alertas). |
| `RTSP_URL_1` … `RTSP_URL_4` | Dirección de cada cámara (`rtsp://usuario:clave@IP:554/...`). El número es el id de la cámara. |
| `ANTHROPIC_API_KEY` | Detección de productos de la caja. |
| `GEMINI_API_KEY_*`, `GROQ_API_KEY_*` | Reconocimiento de personas entre cámaras (Re-ID). |

> **Ojo:** la `DATABASE_URL` del `.env` es la base real. Todo lo que hagas desde tu computadora (por ejemplo, analizar una cámara) se guarda ahí.

## Instalación (una sola vez)

```powershell
# 1. Backend
pip install -r frontend/requirements.txt

# 2. Análisis de cámaras en vivo (además de lo anterior)
pip install ultralytics==8.4.45 "lap>=0.5.12" opencv-python numpy pillow requests tqdm python-dotenv psycopg2-binary mss anthropic groq google-genai

# 3. Frontend
cd frontend
npm ci
```

> Si tenés que reinstalar las dependencias del frontend, **cerrá antes el servidor de desarrollo** (`Ctrl+C`). Con el servidor abierto, Windows bloquea archivos y `node_modules` puede quedar roto.

## Levantar el sistema (desarrollo)

Se usan tres terminales, desde la raíz del repo.

**Terminal 1: backend** (API en http://localhost:8080)

```powershell
cd frontend
python serve_dashboard.py
```

**Terminal 2: frontend** (panel en http://localhost:5173; usá esta dirección mientras desarrollás)

```powershell
cd frontend
npm run dev
```

**Terminal 3: análisis de cámaras en vivo**

```powershell
python -m deteccion.main --rtsp 2
```

- El número es el id de la cámara (1 a 4): `1` Caja Frente Full, `2` Cámara Esquina Full, `3` Caja Full 2, `4` Full Cajas. La dirección sale de `RTSP_URL_<id>` en el `.env`.
- Por defecto no abre ninguna ventana: el seguimiento se ve por consola (para verla, poné `RTSP_MOSTRAR_PREVIEW = True` en `deteccion/config.py`). Va guardando en la base, de a poco, las personas, trayectorias, eventos, mapas de calor y alertas.
- Para cerrarlo y guardar lo que falta: `Ctrl+C` (o la tecla `q`, si la ventana está activada).
- Para analizar varias cámaras hay que abrir una terminal por cámara.

Otros modos de análisis (no guardan en la base de datos):

```powershell
python -m deteccion.main --webcam        # cámara de la computadora (opcional: --webcam 1)
python -m deteccion.main --screen        # pantalla en vivo (opcional: --screen 2)
python -m deteccion.main                 # video grabado: el que indique VIDEO_PATH en deteccion/config.py
```

> Los comandos de `deteccion` se corren siempre **desde la raíz del repo**, no desde dentro de la carpeta.

### Sin servidor de desarrollo (todo en el puerto 8080)

```powershell
cd frontend
npm run build
python serve_dashboard.py       # el panel y la API quedan en http://localhost:8080
```

## Sección Productos (cámara del celular)

1. Instalá en el celular **IP Camera Lite** (iPhone) o **IP Webcam** (Android) y activá su servidor. El celular y la computadora tienen que estar en la **misma red Wi-Fi**.
2. Comprobá en el navegador de la computadora que se ve el video en `http://IP-DEL-CELULAR:8081/video` (IP Webcam usa el puerto `8080`).
3. En el panel, sección Productos: elegí "Cámara del celular", pegá la dirección (`http://admin:admin@IP-DEL-CELULAR:8081/video`) y encendé la cámara.

### Desde el panel de producción (agente local)

El servidor de internet no puede ver la red del local, así que la cámara y el detector los pone la computadora de la caja, la misma que está conectada al celular:

1. Conectá el celular a la computadora (misma red Wi-Fi o la zona con cobertura de la computadora) y abrí el servidor de IP Camera Lite.
2. En esa computadora, desde `frontend/`:
   ```powershell
   py -3.13 serve_dashboard.py --agente
   ```
   Se abre el panel de producción (https://optifull.onrender.com). Iniciá sesión y entrá a Productos.
3. Si Chrome pregunta si la página puede acceder a dispositivos de la red local, tocá **Permitir** (una sola vez).
4. Seguí como siempre: dirección de la cámara, switch, confirmar productos y venta.

El video va del celular a la computadora y de ahí a la pantalla, sin pasar por internet (igual de fluido que en local), y el detector corre en la computadora como siempre. Las decisiones y las ventas pasan por Supabase, que es la misma base que lee producción. Desde otra computadora el panel de producción funciona igual, salvo la cámara: si no encuentra el agente, Productos muestra cómo iniciarlo.

El agente (`frontend/api/agente.py`) solo atiende pedidos de la propia computadora y solo acepta órdenes de las páginas de producción y QA (variable `AGENTE_ORIGENES` para cambiarlas).

## Inicio de sesión y roles

Las cuentas están en la base de datos (tablas `usuarios`, `roles`, `sucursales`). Hay dos roles:

| Rol | Quiénes | Secciones del panel |
| --- | --- | --- |
| `administrador` | Dueños y gerentes | Todas |
| `usuario` | Empleados | Productos, Ventas y Alertas |

Al iniciar sesión, el servidor deja una cookie firmada (`HttpOnly`) y **toda la API la exige**: sin sesión responde 401 (ver `frontend/api/sesion.py`). Solo quedan abiertos el login, `/api/health`, el formulario de la landing y los datos que muestra la landing (`/api/stats` y el mapa de calor). Los permisos por rol todavía se aplican solo en el panel: la API verifica que haya una sesión, no el rol.

Para crear una cuenta (la clave se guarda hasheada):

```powershell
python db/crear_usuario.py --usuario agos --nombre "Agostina Blason" --rol administrador --cargo dueno
```

## Pruebas

```powershell
cd test
python -m pytest                 # backend y detección

cd ../frontend
npm test                         # permisos por rol
npx oxlint src                   # análisis estático del frontend
```

## Base de datos

El esquema está en `db/schema.sql`. **No lo ejecutes completo sobre una base con datos** (`python db/create_db.py` incluye un `DROP TABLE productos CASCADE` y borraría los productos). Para cambios nuevos, aplicá solo las sentencias que correspondan.

## Despliegue

Cada push a `main` dispara el pipeline de GitHub Actions (`.github/workflows/pipeline.yml`): pruebas, comprobación de la base, deploy a QA en Render, pruebas de integración y deploy a producción (con aprobación manual). Antes de desplegar, la base de cada entorno tiene que tener el esquema al día.
