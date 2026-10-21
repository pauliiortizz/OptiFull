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

El p99 no baja porque lo domina el login. Contra Supabase la diferencia debería ser mayor, porque la conexión
cuesta mucho más que contra una base local. Se mide en QA con la próxima corrida del pipeline.
