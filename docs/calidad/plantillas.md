# Plantillas de caso de prueba y de defecto

Se usan para documentar los casos que no son obvios a partir del código del test (clases de equivalencia,
valores límite, tablas de decisión) y para cargar defectos en Jira. El ID del caso o del defecto va en el nombre
o en un comentario del test automatizado, así la trazabilidad requisito → caso → defecto se puede seguir con
`git grep <ID>`.

## Caso de prueba

| Campo | Contenido |
|---|---|
| ID | `CP-<módulo>-<nro>` |
| Requisito | RF / RNF que verifica (ver la matriz de trazabilidad en el [plan de pruebas](plan-de-pruebas.md)) |
| Nivel | Unitario · Persistencia (Postgres real) · Integración · E2E · Carga |
| Técnica | Clases de equivalencia · Valores límite · Tabla de decisión · Escenario |
| Precondiciones | Estado del sistema y datos necesarios |
| Datos de entrada | Valores concretos (uno por clase o por límite) |
| Pasos | Numerados |
| Resultado esperado | Fijado **antes** de ejecutar |
| Test automatizado | `archivo::test` |
| Defectos asociados | `DEF-xxx` |

### Ejemplo: CP-VID-01 · parámetros `t` y `dur` de `/api/sessions/<id>/clip`

| Campo | Contenido |
|---|---|
| Requisito | RF-15 (vista de alertas con evidencia en video) |
| Nivel / técnica | Unitario · clases de equivalencia y valores límite |
| Precondiciones | Sesión 1 con su video en disco; base de datos simulada |
| Clases válidas | `t` número ≥ 0; `dur` número > 0 |
| Clases inválidas | texto (`t=abc`, `dur=diez`), fuera de rango (`t=-1`, `dur=0`, `dur=-5`), no finitos (`t=nan`, `dur=inf`) |
| Valores límite | `t=-1` / `t=0`; `dur=0` / `dur` positivo mínimo |
| Resultado esperado | inválidas → 400 sin consultar la base de datos; sin base → 503 |
| Test automatizado | `test_video.py::test_clip_con_parametros_invalidos_responde_400`, `::test_clip_sin_base_de_datos_responde_503` |
| Defectos asociados | DEF-007 |

## Defecto

| Campo | Contenido |
|---|---|
| ID | `DEF-<nro>` (correlativo, el mismo en Jira, en el commit y en el test) |
| Título | Qué falla, en una línea, desde el punto de vista del usuario |
| Severidad | Crítica · Alta · Media · Baja (criterios en el [registro](defectos.md)) |
| Detectado por | Test unitario · Persistencia · Integración · E2E · Carga · SonarCloud · Pipeline · Revisión |
| Requisito / caso | RF / RNF y `CP-...` o el test que lo cubre |
| Entorno | Local · CI · QA · Producción, con versión o commit |
| Pasos para reproducir | Numerados, con datos concretos |
| Resultado esperado | |
| Resultado obtenido | Con el mensaje de error o la respuesta exacta |
| Test de regresión | `archivo::test` (falla sin el arreglo y pasa con él) |
| Commits | rojo (el test) y verde (el arreglo) |
| Estado | Abierto → En curso → Corregido → Verificado en QA |
