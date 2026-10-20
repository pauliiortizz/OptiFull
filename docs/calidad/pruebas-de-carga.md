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

El primer intento de carga sostenida no cumplió el mínimo de pedidos ni el p99, y tuvo pedidos de ~210 s. No
fue OptiFull: los eventos 506/507 de Windows (Modern Standby) muestran la PC suspendida de 17:58 a 18:01 y de
18:01 a 18:11. Los umbrales hicieron lo que tenían que hacer: la corrida anómala quedó en rojo y no pasó como
buena. En el pipeline no ocurre, porque corre en un runner de GitHub.

### QA (pipeline)

Se completa con la primera ejecución en `main` que incluya el job `carga-qa` (enlace a la ejecución y números
del resumen).
