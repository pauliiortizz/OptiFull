# 4 · Métricas y análisis estático

Fuente de los números: análisis de SonarQube Cloud de `main` (e540c94, 21/10/2026), carpeta `frontend/`, salvo
que se indique otra cosa. El análisis estático corre en el pipeline en cada push: Ruff en build-test (bloquea por
errores probables) y SonarQube Cloud en el job `calidad` (con el quality gate).

## Métricas interpretadas

No alcanza con el valor: para cada métrica, dónde se concentra y qué consecuencia tiene.

| Métrica | Tipo | Valor | Dónde se concentra | Interpretación y consecuencia |
|---|---|---|---|---|
| **Tamaño** (líneas de código) | Producto | 10 451: API 3 529, panel 6 922 | `index.css` (1 418), `App.jsx` (625), `SectionPages.jsx` (552), `reportes_datos.py` (526) | El panel es dos tercios del módulo. `App.jsx` concentra la navegación, el dashboard y la sesión: es el archivo que más se toca y el más riesgoso de cambiar. |
| **Complejidad ciclomática** | Producto | 2 391 en total; 8 funciones de la API por encima de 10; la mayor, `generar_pdf()`, con 21 | Por archivo: `App.jsx` (256), `SectionPages.jsx` (181), `ProductosPage.jsx` (168), `FloorPlan.jsx` (160) | `generar_pdf()` cae en el rango 21-50 (compleja, alto riesgo, difícil de probar): necesita muchos casos para cubrir sus caminos. Su complejidad cognitiva, 40, es la más alta del módulo (el umbral de SonarQube es 15). |
| **Duplicación** | Producto | 1,0 % en el módulo; 2,7 % en la API | **`video.py`, 19,7 %**: `session_tracking()` y `camera_tracking()` repiten dos bloques de 22 y 28 líneas | El total está muy por debajo del umbral del gate (5 %), pero en un archivo está casi cuatro veces por encima. Un promedio bajo esconde concentraciones: un defecto en esas líneas habría que corregirlo dos veces. |
| **Cobertura** (sentencia + decisión) | Producto | 94,5 %: líneas 96,8 %, ramas 90,2 %; API 98,0 %, panel 91,6 % | Lo menos cubierto: `efectos/iman.js` (25 %: 82 líneas y 100 ramas sin cubrir), `correo.py` (81 %), `ReportData.jsx` (87 %) | Lo no cubierto es código que llegó con el rediseño visual (el efecto imán del cursor) y el aviso por email. Una cobertura alta no garantiza que no haya defectos (principio 1), pero una baja en un archivo sí marca dónde no se sabe si anda. |
| **Densidad de defectos** | Producto | 1,9 defectos por KLOC (20 en 10,45 KLOC) | API: 13 en 3,53 KLOC (**3,7 por KLOC**); panel: 7 en 6,92 KLOC (1,0 por KLOC) | La API tiene casi cuatro veces más defectos por línea que el panel: es la que recibe datos del usuario (rutas, URLs, cabeceras) y habla con Supabase y Render. Ahí conviene concentrar la revisión y las pruebas de seguridad. |
| **Acoplamiento** | Producto | 9 módulos de la API dependen de `db._get_conn()` (alertas, health, heatmap, login, productos, reportes, reportes_export, stats, video) | `frontend/api/db.py` | Un cambio en `_get_conn()` afecta a casi toda la API. Por eso el pool de conexiones se hizo sin cambiar su interfaz (los endpoints siguen llamando a `close()`), y con tests propios contra un Postgres real. |
| **Problemas de mantenibilidad** (code smells) | Producto | 200; ninguno bloqueante | `SectionPages.jsx` (30), `LandingPage.css` (12); por regla: 33 ternarios anidados, 14 imports sin usar, 10 funciones con complejidad cognitiva mayor a 15 | No rompen nada hoy, pero hacen más lento cada cambio. Los imports sin usar son los más baratos de corregir. |
| **Bugs** | Producto | 13, ninguno crítico | 11 son de accesibilidad (S1082: elementos con clic sin manejo de teclado), en el panel | Afectan al objetivo U4 (que todo se use con teclado), que es el único objetivo de usuario sin cumplir. |

## Métrica de proceso

**Tasa de ejecuciones en verde del pipeline en `main`, y la causa de cada falla.** Mide cómo trabaja el equipo,
no el código. Desde que se incorporó el quality gate (20/10):

| Commit | Fecha | Resultado | Causa |
|---|---|---|---|
| b877bde | 20/10 16:52 | ❌ Quality gate | Primer análisis con el gate: las dos observaciones bloqueantes de fpdf2 (DEF-001) y poca cobertura sobre código nuevo |
| ae717d3 | 20/10 18:48 | Cancelada | — |
| 67935ce | 20/10 20:51 | ❌ Quality gate | Código nuevo del panel (rediseño visual) sin tests: cobertura sobre código nuevo de 73 % |
| ba9b344 | 21/10 16:56 | ❌ E2E | El test suponía una cuenta de administrador; la de QA es de empleado (defecto del test, no del producto) |
| e54cbfa | 21/10 17:21 | ❌ Stress | p95 de 7,6 s: la API abría una conexión a Supabase por pedido |
| 0cf1129 | 21/10 17:56 | ❌ Stress | p95 de 8,2 s con 8 hilos: la hipótesis de los hilos era incorrecta |
| 9d83e92 | 21/10 18:35 | ❌ E2E | Carrera del test: verificaba la sesión antes de que llegara la respuesta del logout |
| **876f0cb** | **21/10 19:00** | ✅ | Pipeline completo en verde, con el pool de conexiones |
| e540c94 | 21/10 19:52 | ✅ | Arreglos de seguridad (DEF-023 a DEF-027) |

**Interpretación.** De 8 ejecuciones terminadas, 2 en verde (25 %). Una tasa baja no es mala en sí: **ninguna de
las 6 fallas llegó a producción**, y cada una tuvo una causa concreta que se corrigió con un cambio y, cuando era
un defecto, con su test. Tres eran del producto (cobertura, conexión por pedido), dos eran de los propios tests
(supuestos del E2E) y una fue una hipótesis descartada con datos. La métrica que acompaña es el **tiempo hasta
volver al verde**: 26 h la primera vez (había que escribir los tests que faltaban) y 2 h para la serie del 21/10
(16:56 → 19:00). En la rama de trabajo, el feedback de build-test es de 1,6 minutos de media (32 de 41 ejecuciones
en verde).

## Métrica de proyecto

**Desvío del cronograma.** El 20/10 se planificó terminar en seis días (20 al 25/10):

| Día planificado | Tarea | Hecho |
|---|---|---|
| 20/10 | Falsos positivos de SonarQube Cloud, proyecto en Jira, tests de la API | 20/10 (Jira, el 21/10) |
| 21/10 | Tests de `deteccion/` y `deteccion_productos/` (fuera del TP) | 20/10 |
| 22/10 | Tests del panel y defecto rojo/verde | 20/10 |
| 23/10 | Smoke en QA, E2E, stress y carga sostenida | 21/10 |
| 24/10 | Plan de pruebas, riesgos, ISO 25010, herramienta nueva | 20 y 21/10 |
| 25/10 | Despliegue final en verde y números del informe | 21/10 (primer verde completo) |

Desvío = (duración real − planificada) / planificada = (2 − 6) / 6 = **−67 %**: se terminó cuatro días antes. La
interpretación no es "se planificó mal" sino que el plan suponía trabajo manual que se automatizó y que se usó IA
para escribir los primeros borradores (ver [uso-de-ia.md](uso-de-ia.md)); el tiempo ganado se usó en lo que el
plan no tenía: la revisión de las vulnerabilidades y el informe.

## Hallazgos

Tres hallazgos del análisis estático, con su prioridad para la próxima versión:

| # | Dónde | Problema | Por qué importa | Mejora posible | Prioridad |
|---|---|---|---|---|---|
| H1 | `frontend/src`, 11 lugares (por ejemplo `App.jsx:630`, `SectionPages.jsx:233`) | Elementos con `onClick` que no se pueden activar con el teclado (regla S1082) | Una persona que usa solo el teclado no llega a esas acciones: es el objetivo U4, el único de usuario que no se cumple | Usar `<button>` en vez de `<div onClick>`, o agregar `onKeyDown` y `tabIndex`; un test por rol accesible para cada uno | **Alta**: afecta a usuarios, esfuerzo bajo |
| H2 | `frontend/api/video.py`: `session_tracking()` y `camera_tracking()` | 19,7 % de líneas duplicadas: los dos endpoints arman las trayectorias y los límites del plano con el mismo código | Un defecto en ese armado hay que corregirlo dos veces; ya pasó en este archivo con los rangos de video (DEF-005 a 007) | Extraer la parte común a una función `_tracking_de_personas(cur, personas)`; los tests actuales de los dos endpoints sirven de red | **Media**: riesgo medio, esfuerzo bajo |
| H3 | `frontend/api/reportes_formatos.py`: `generar_pdf()` | Complejidad ciclomática 21 y cognitiva 40: arma todas las secciones del PDF en una sola función | Es la función más difícil de cambiar del módulo; cada sección nueva del reporte agrega ramas | Una función por sección del PDF y una tabla que las recorra; mantener los tests de `test_reportes_formatos.py` | **Media-baja**: tiene tests que la cubren, esfuerzo medio |

Y uno que no viene de una herramienta sino de armar el plan de contingencia:

| # | Dónde | Problema | Prioridad |
|---|---|---|---|
| H4 | `frontend/api/leads.py` | Los pedidos de demo se guardan en `leads.jsonl`, en el disco de Render, que se borra en cada deploy; si el email falla, la landing pide reintentar y el pedido queda duplicado (riesgo R9) | **Alta** si la landing se usa para conseguir clientes; el arreglo (guardarlos en Supabase) es de la tesis |

**Priorización para la próxima versión:** H1 (impacto en usuarios y es barato), H4 (pérdida de datos de
clientes), H2 (barato y reduce el riesgo en el archivo con más defectos). H3 queda después porque sus tests ya
protegen los cambios.

## Flujo de control

Dos casos encontrados leyendo el código, sin ejecutarlo:

**1. Una rama defensiva que no se puede cumplir.** En `frontend/api/video.py`, `_stream_video()`:

```python
rango = _rango_pedido(request.headers.get('Range'), size)   # devuelve (inicio, fin) con 0 <= inicio <= fin <= size - 1
...
    rem = length                       # length = fin - inicio + 1
    while rem > 0:
        chunk = f.read(min(65536, rem))
        if not chunk:                  # <- ¿cuándo se cumple?
            break
```

`_rango_pedido()` (corregido en DEF-006) garantiza que el fin no pasa del último byte del archivo, así que nunca se
piden más bytes de los que quedan: `f.read()` no puede devolver vacío antes de terminar. La condición solo se
cumpliría si el archivo se achica mientras se está enviando. Es una rama defensiva: no es un error, pero es código
que las pruebas no pueden alcanzar (el `break` de la línea 82 es una de las 4 líneas sin cubrir de `video.py` en el
reporte de cobertura) y conviene
dejar un comentario que diga por qué está.

**2. Una asignación que nunca tiene efecto.** En `frontend/src/pages/PagesHeatmapCameras.jsx`, `Switch`:

```jsx
style={{
  appearance: "none", border: 0, padding: 0, ...
  background: on ? ... , border: `1px solid ${on ? "var(--pos-soft)" : "var(--line)"}`,
```

`border` aparece dos veces en el mismo objeto: la segunda pisa a la primera, así que `border: 0` nunca se aplica.
SonarQube Cloud lo marca como bug (S1534). El comportamiento es el esperado (gana el borde con color), pero quien lea
el código puede creer que el botón no tiene borde.

## Mejora medida antes y después

La mejora del módulo es la de **eficiencia de desempeño**: el pool de conexiones a Supabase. Mismo escenario
(stress de 40 usuarios contra QA), mismo umbral, antes y después:

| | Antes (4 hilos, una conexión por pedido) | Intento descartado (8 hilos) | Después (pool de conexiones) |
|---|---|---|---|
| Pedidos atendidos | 2 205 | 2 141 | **3 508** (+59 %) |
| Mediana | 1 500 ms | 1 600 ms | **100 ms** |
| p95 | 7 600 ms ❌ | 8 200 ms ❌ | **2 400 ms** ✅ |
| p99 | 13 000 ms ❌ | 14 000 ms ❌ | **9 400 ms** ✅ |
| Errores | 0 % | 0 % | 0 % |

Detalle por endpoint y lectura en [pruebas-de-carga.md](pruebas-de-carga.md). Y la mejora de proceso que hizo
posible todo lo demás: la cobertura de la API pasó de **26 % a 98 %** ([alcance-medicion.md](alcance-medicion.md)).

## Reflexión: ¿un programa que pasa sus tests tiene buena calidad interna?

No necesariamente, y el TP lo mostró dos veces. Con todos los tests en verde, la API tardaba 7,6 s bajo carga
(calidad externa) y `video.py` tenía un 19,7 % de código duplicado (calidad interna). Los tests verifican lo que
alguien pensó en verificar. Las métricas y el análisis estático miran lo que nadie pensó: dónde se concentra la
complejidad, qué se repite, qué no se cubre. Por eso el pipeline usa las dos cosas.
