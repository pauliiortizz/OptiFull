# Alcance de la medición de calidad

Qué código de OptiFull se mide (cobertura, análisis estático, quality gate) y qué
queda afuera, con su justificación. La configuración que lo aplica está en:

- `pyproject.toml`: Ruff y cobertura de Python (`[tool.coverage]`).
- `sonar-project.properties`: SonarQube Cloud.

## Qué se mide

| Carpeta | Qué es | Se mide |
|---|---|---|
| `frontend/api/` | Backend Flask desplegado en Render (QA y producción) | ✅ |
| `frontend/src/` | Panel web React | ✅ |
| `deteccion/` | Análisis de cámaras: YOLO, tracking, heatmaps, Re-ID, persistencia | ✅ (incluido `main.py`) |
| `deteccion_productos/` | Detección de productos en la caja | ✅ |

## Qué no se mide y por qué

| Carpeta / archivo | Motivo |
|---|---|
| `deteccion/mantenimiento/` | Scripts de corrección de datos que se ejecutan una sola vez a mano. No forman parte del flujo del sistema. |
| `deteccion_productos/test_*.py` | Scripts de prueba manuales (se corren con `python test_x.py`). No son código del producto. |
| `frontend/serve_dashboard.py` | Script para levantar el sistema en desarrollo. En el despliegue se usa `gunicorn`. |
| `test/`, `frontend/src/**/*.test.js` | Son los propios tests: se analizan como tests, no como código a cubrir. |
| `db/`, `docker/`, `.github/` | Infraestructura: esquema de base de datos, imagen Docker y pipeline. |
| `.agents/`, `.aider-desk/`, `.claude/` | Skills de herramientas de IA que usa el equipo. No son código del producto. |
| `ultralytics` | Librería de terceros (YOLO). Se instala con pip (`ultralytics==8.4.45`), ya no está copiada en el repo. |

## Cómo se mide

- **Cobertura de Python:** sentencia y decisión (`branch = true`), con `pytest-cov`.
- **Cobertura del frontend:** test runner de Node (`npm run test:coverage`), reporte LCOV.
- **Análisis estático:** Ruff en cada push (bloquea por errores probables: reglas `E9`, `F` y `B`)
  y SonarQube Cloud en cada push a `main`.
- **Quality gate** (`.github/scripts/quality_gate.py`): frena el pipeline si hay bugs críticos
  abiertos, si la duplicación supera el 5 % o si la cobertura sobre código nuevo es menor al 80 %.

## Línea base (20/10/2026, antes de los puntos 3 a 6)

| Medida | Valor |
|---|---|
| Tests unitarios | 165, todos pasan |
| Cobertura Python (sentencia + decisión) con este alcance | 21 % |
| Observaciones de Ruff que bloquean (`E9`, `F`, `B`) | 31 → 0 (corregidas) |
| Observaciones de Ruff de complejidad y estilo (no bloquean) | 226 |
| Función más compleja | `deteccion/main.py: main()`, complejidad ciclomática 91 (umbral 10) |
