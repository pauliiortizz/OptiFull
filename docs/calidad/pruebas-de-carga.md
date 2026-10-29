# Pruebas de carga: stress y esfuerzo sostenido

Código: [`test/carga/locustfile.py`](../../test/carga/locustfile.py) (escenarios) y
[`test/carga/verificar_umbrales.py`](../../test/carga/verificar_umbrales.py) (umbrales). Corren en el job
`carga-qa` del pipeline después del E2E, contra QA en Render con la base de QA en Supabase. Si un umbral no se
cumple, el job queda en rojo y **no se despliega a producción**.

## Escenario

Cada usuario virtual hace lo mismo que una persona con el panel abierto: inicia sesión una vez y después, con
pausas de 1 a 3 segundos, consulta:

| Pedido | Peso | Por qué |
|---|---|---|
| `GET /api/stats` | 4 | KPIs del dashboard: la consulta más pesada y la más frecuente |
| `GET /api/personas` | 3 | Lista de visitas |
| `GET /api/alertas` | 3 | Feed de alertas (el panel lo refresca solo) |
| `GET /api/heatmap/latest` | 2 | Último mapa de calor (Supabase Storage) |
| `GET /api/reportes/opciones` | 1 | Pantalla de reportes |
| `GET /api/health` | 1 | Lo usa Render y el pipeline |
| `GET /` | 1 | El frontend compilado |

Solo lecturas: las pruebas de carga no escriben en la base de QA.

## Perfiles

| Perfil | Carga | Duración | Qué busca |
|---|---|---|---|
| **Stress** | Escalones de 5 → 10 → 20 → 30 → 40 usuarios, uno por minuto | 6 min | Hasta dónde aguanta el plan gratuito de Render (512 MB, 1 worker con 4 hilos) y cómo se degrada |
| **Esfuerzo sostenido** | 15 usuarios constantes | 10 min | Que el servicio no se degrade con el tiempo: memoria, conexiones a la base que no se liberan |

15 usuarios es más que el equipo de una tienda (dueño, gerente y empleados de un turno); 40 es casi el triple.

## Umbrales

| Umbral | Stress | Sostenida | Por qué |
|---|---|---|---|
| Errores | ≤ 5 % | ≤ 1 % | Bajo stress se acepta alguna falla, nunca que se caiga; con la carga esperada, prácticamente ninguna |
| p95 | ≤ 5 s | ≤ 2 s | 2 s es lo máximo que alguien espera que cargue un panel sin pensar que se colgó |
| p99 | ≤ 10 s | ≤ 5 s | Acota los casos peores (arranque en frío, consultas a Supabase desde Render) |
| Pedidos realizados | ≥ 500 | ≥ 1500 | Que la corrida haya ocurrido de verdad (un servicio caído "responde rápido" con 0 pedidos) |
| p95 del último tercio / p95 del primero | — | ≤ 2 | Degradación con el tiempo |

Los valores son el punto de partida; se revisan con los resultados de las primeras corridas en QA y cualquier
cambio se registra en la tabla de versiones del [plan de pruebas](plan-de-pruebas.md).

## Reportes que deja el pipeline

En el artefacto `carga-qa` de cada ejecución: `stress.html` y `sostenida.html` (reporte de Locust con los
gráficos de usuarios, pedidos por segundo y tiempos de respuesta en el tiempo), los CSV con los datos y
`*_umbrales.json` con el resultado de cada umbral. La tabla de umbrales y la de cada endpoint también se
publican en el resumen de la ejecución en GitHub Actions.

## Resultados

### Local (20/10/2026)

Contra el sistema levantado en una PC del equipo (Flask con hilos, Postgres local vacío). Sirve para validar
los scripts y como referencia; **los números del informe son los de QA**, que tienen la red hasta Supabase y
los límites de Render.

| Perfil | Pedidos | Errores | p50 | p95 | p99 | Pedidos/s | Resultado |
|---|---|---|---|---|---|---|---|
| Stress | 4151 | 0 % | 84 ms | 170 ms | 280 ms | 11,5 | ✅ |
| Sostenida (1.er intento) | 992 | 0 % | 170 ms | 420 ms | 2000 ms | 2,8 | ❌ inválido: la PC se suspendió dos veces durante la corrida |
| Sostenida (2.º intento) | 4266 | 0 % | 92 ms | 180 ms | 320 ms | 7,1 | ✅ degradación del p95: 1,19× |

El primer intento de carga sostenida no cumplió el mínimo de pedidos ni el p99, y tuvo pedidos de ~210 s. No
fue OptiFull: los eventos 506/507 de Windows (Modern Standby) muestran la PC suspendida de 17:58 a 18:01 y de
18:01 a 18:11. Los umbrales hicieron lo que tenían que hacer: la corrida anómala quedó en rojo y no pasó como
buena. En el pipeline no ocurre, porque corre en un runner de GitHub.

### QA (pipeline)

Primera corrida contra QA en Render ([ejecución 39643083288](https://github.com/pauliiortizz/OptiFull/actions/runs/39643083288),
commit e54cbfa, 21/10/2026), con gunicorn en 1 worker y **4 hilos**:

| Perfil | Pedidos | Errores | p50 | p95 | p99 | Pedidos/s | Resultado |
|---|---|---|---|---|---|---|---|
| Stress | 2205 | 0 % | 1500 ms | 7600 ms | 13000 ms | 6,1 | ❌ p95 y p99 por encima del umbral |
| Sostenida | — | — | — | — | — | — | ✅ cumplió todos los umbrales |

Stress por endpoint (ms):

| Endpoint | p50 | p95 | p99 |
|---|---|---|---|
| `GET /` (frontend) | 850 | 2500 | 13000 |
| `GET /api/alertas` | 1600 | 5500 | 12000 |
| `GET /api/health` | 1300 | 8200 | 17000 |
| `GET /api/heatmap/latest` | 1300 | 3300 | 13000 |
| `GET /api/personas` | 1700 | 6400 | 11000 |
| `GET /api/reportes/opciones` | 1600 | 7600 | 11000 |
| `GET /api/stats` | 1700 | 7700 | 14000 |
| `POST /api/login` | 8100 | 18000 | 18000 |

**Lectura.** Con la carga esperada el sistema cumple; con casi el triple no se cae (0 % de errores) pero se
pone lento. No es un endpoint lento: hasta `/api/health`, que casi no hace nada, llega a 8,2 s de p95. Es cola:
con 4 hilos, a 40 usuarios hay más pedidos que hilos, y cada uno ocupa su hilo mientras espera a Supabase (cada
pedido abre además una conexión nueva). El login es el más lento porque el hash de la clave (pbkdf2) es CPU pura.
El umbral hizo su trabajo: el job quedó en rojo y no se desplegó a producción.

**Primer intento: 8 hilos (descartado).** Se subieron los hilos de gunicorn de 4 a 8 y el stress no mejoró:

| Stress | Pedidos | Errores | p50 | p95 | p99 |
|---|---|---|---|---|---|
| 4 hilos | 2205 | 0 % | 1500 ms | 7600 ms | 13000 ms |
| 8 hilos | 2141 | 0 % | 1600 ms | 8200 ms | 14000 ms |

El límite no eran los hilos sino la CPU: el plan gratuito de Render da 0,1 CPU, y con más hilos esa misma CPU
se reparte entre más pedidos. Se volvió a 4 hilos. El login empeoró (mediana de 8,1 s a 12 s): el hash de la
clave (pbkdf2) es CPU pura.

**Segundo intento: pool de conexiones.** Cada pedido abría una conexión nueva a Supabase (TCP + TLS +
autenticación, ~1,3 s medido en vivo, y CPU para el TLS). Ahora `frontend/api/db.py` mantiene hasta 5
conexiones abiertas y cada pedido usa una prestada; los endpoints no cambiaron (su `close()` la devuelve al
pool). Tests en `test/bd/test_pool.py`. Medido local (30 usuarios, 90 s, misma máquina y misma base):

| | Sin pool | Con pool |
|---|---|---|
| `GET /api/health` p50 / p95 | 36 / 61 ms | 7 / 13 ms |
| `GET /api/stats` p50 / p95 | 78 / 180 ms | 9 / 15 ms |
| `GET /api/personas` p50 / p95 | 42 / 74 ms | 7 / 12 ms |
| Total p50 / p95 / p99 | 47 / 150 / 800 ms | 8 / 29 / 790 ms |

El p99 no baja porque lo domina el login.

**Resultado en QA con el pool** ([ejecución 39657822881](https://github.com/pauliiortizz/OptiFull/actions/runs/39657822881),
commit 876f0cb, 21/10/2026): **el pipeline completo en verde**, con el deploy a producción incluido.

| Stress (40 usuarios) | Pedidos | Errores | p50 | p95 | p99 | Pedidos/s | Resultado |
|---|---|---|---|---|---|---|---|
| 4 hilos, sin pool | 2205 | 0 % | 1500 ms | 7600 ms | 13000 ms | 6,1 | ❌ |
| 8 hilos, sin pool | 2141 | 0 % | 1600 ms | 8200 ms | 14000 ms | 5,9 | ❌ |
| **4 hilos, con pool** | **3508** | **0 %** | **100 ms** | **2400 ms** | **9400 ms** | **9,7** | ✅ |

| Esfuerzo sostenido (15 usuarios, 10 min) | Pedidos | Errores | p50 | p95 | p99 | Pedidos/s | Degradación del p95 | Resultado |
|---|---|---|---|---|---|---|---|---|
| 4 hilos, con pool | 4192 | 0 % | 89 ms | 140 ms | 510 ms | 7,0 | 0,58 | ✅ |

Por endpoint, stress sin pool → con pool (p50 / p95, ms):

| Endpoint | Sin pool | Con pool |
|---|---|---|
| `GET /` (frontend) | 850 / 2500 | 69 / 2200 |
| `GET /api/alertas` | 1600 / 5500 | 93 / 650 |
| `GET /api/health` | 1300 / 8200 | 80 / 1400 |
| `GET /api/heatmap/latest` | 1300 / 3300 | 89 / 570 |
| `GET /api/personas` | 1700 / 6400 | 120 / 2100 |
| `GET /api/reportes/opciones` | 1600 / 7600 | 87 / 1400 |
| `GET /api/stats` | 1700 / 7700 | 120 / 1400 |
| `POST /api/login` | 8100 / 18000 | 7400 / 13000 |

**Lectura.** El pool bajó la mediana del stress 15 veces (1500 → 100 ms) y el p95 a un tercio (7600 → 2400 ms), y
con la misma CPU se atendió un 59 % más de pedidos (6,1 → 9,7 por segundo). La causa era la que se pensaba: el
costo de abrir una conexión por pedido, no la cantidad de hilos. Con la carga esperada (sostenida), el p95 queda
en 140 ms, catorce veces por debajo del umbral, y no se degrada con el tiempo (0,58: el final fue más rápido que
el arranque, cuando el pool todavía abría sus conexiones).

**Lo que queda.** El login sigue siendo lo más lento (mediana de 6,3 a 7,4 s en QA) y es el que estira el p99:
el hash pbkdf2 de la clave está pensado para costar CPU, y el plan gratuito tiene 0,1. En el uso real es un pedido
por persona y por turno, así que no se tocó; bajar las iteraciones del hash haría más fácil adivinar claves si se
filtrara la base. Si hiciera falta, la alternativa es más CPU (un plan pago de Render), no un hash más débil.

**Un solo login por prueba (28/10/2026).** Con el pool, el stress quedó al límite del p99: 9,4 s en verde y
después 11 s en rojo sin cambios en la API (p95 2,8 s, 0 % de errores). Todos los endpoints tenían el p99 entre
10 y 11 s: cada escalón sumaba 10 usuarios y cada uno hacía su login (pbkdf2) en el arranque, y esa ráfaga de CPU
frenaba a todos los pedidos que llegaban en ese momento. Eso no es el uso real (un login por persona y por turno),
así que `test/carga/locustfile.py` ahora inicia sesión una vez al arrancar la prueba y todos los usuarios virtuales
usan esa cookie. El stress mide las lecturas bajo carga; el login sigue en el reporte como un pedido.
