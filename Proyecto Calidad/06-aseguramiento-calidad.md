# 6 · Aseguramiento de la calidad

## Plan de pruebas

El plan está en [plan-de-pruebas.md](plan-de-pruebas.md) y se versiona junto con el código: cada cambio de alcance,
criterio o umbral agrega una fila a su tabla de versiones (va por la 3.0). Contiene el alcance (el módulo de
interfaz web), los niveles y la pirámide, los entornos y los datos, los **criterios de entrada, de salida y de
suspensión**, los riesgos, la técnica de diseño de casos y la **trazabilidad requisito → caso → defecto**.

Los criterios de salida son los que deciden si un cambio llega a producción, y todos los verifica el pipeline:
pruebas al 100 %, cobertura ≥ 80 % (existente y nueva), 0 bugs críticos, duplicación ≤ 5 %, smoke, integración y
E2E en QA, umbrales de carga, y ningún defecto crítico o alto abierto.

## Riesgos: probabilidad × impacto

Los riesgos de producto (R1 a R9) y de proyecto (RP1 a RP5) están detallados en el plan, con su mitigación. Así
quedan en la matriz:

| Probabilidad ↓ / Impacto → | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| **5** | R8 | | | | |
| **4** | | | RP2 | R1 | |
| **3** | | | R4, R5, R6, RP3 | RP4 | R2, R3 |
| **2** | | | R9 | R7, RP5 | RP1 |
| **1** | | | | | |

Los de la zona alta (exposición ≥ 15: R1 dependencias, R2 seguridad, R3 Supabase) son los que concentran las
pruebas: tests de seguridad, smoke de sesión, pruebas sin base de datos y la instalación de dependencias de cero en
cada push. R8 (arranque en frío) es muy probable pero de impacto mínimo, por eso solo se mitiga con timeouts.

## QA y QC

QA mejora **cómo** trabaja el equipo (proceso, preventivo); QC revisa **lo que** el equipo produjo (producto,
detección). Las prácticas del TP, clasificadas:

| Práctica | QA o QC | Por qué |
|---|---|---|
| Definir los umbrales del quality gate antes de escribir los tests | QA | Fija el estándar que el proceso tiene que cumplir |
| Escribir y versionar el plan de pruebas | QA | Decide qué se prueba, cómo y con qué criterios |
| Regla de trabajo: primero el test que falla, después el arreglo | QA | Cambia la forma de corregir: ningún arreglo sin su regresión |
| Elegir SonarQube Cloud con el proceso de cinco pasos | QA | Decisión sobre la herramienta del proceso |
| Traer `main` a la rama y correr todas las suites antes de cada PR | QA | Previene que un cambio de otra rama rompa lo que ya andaba (riesgo R6) |
| Lineamientos para el uso de IA ([uso-de-ia.md](uso-de-ia.md)) | QA | Define cómo se revisa lo que la IA genera |
| Ejecutar las pruebas unitarias, de integración y E2E en el pipeline | QC | Detecta defectos en el producto construido |
| Ejecutar el stress y la carga sostenida contra QA | QC | Mide el producto desplegado |
| Análisis estático de SonarQube Cloud y revisión de sus 10 vulnerabilidades | QC | Inspección del código |
| Registrar cada defecto en Jira con pasos, esperado y obtenido | QC | Seguimiento de defectos encontrados |
| Verificar en el pipeline que el arreglo funciona antes de cerrar el defecto | QC | Confirmación con evidencia (ver abajo) |

**Lo que el QC no ve sin QA.** El E2E pasa en cada deploy, pero con la cuenta de empleado: el recorrido del
administrador (Dashboard y Reportes) no se prueba en QA. Ningún test va a fallar por eso; es una decisión del
proceso (qué cuenta usa el pipeline) que hay que tomar. Es la misma lección del caso Boeing 737 MAX: un producto
puede pasar todo el QC si el proceso no consideró los escenarios correctos.

## Ciclo de vida de un defecto

```
 Detectado ──► Registrado ──► Reproducido ──► Corregido ──► Verificado ──► Cerrado
 (test, gate,   (Jira KAN,    (test de        (commit       (pipeline en    (estado
  revisión)      pasos,        regresión en    verde)        verde con el    Completado
                 esperado,     rojo)                         test)           en Jira)
                 obtenido)
```

"Corregido por quien lo programó" no es lo mismo que "verificado": un defecto se cierra en Jira recién cuando el
pipeline, que no es la persona que lo arregló, pasa con su test de regresión. Los 20 defectos del módulo web
siguieron este ciclo ([defectos.md](defectos.md)).

## Independencia de las pruebas

| Nivel de independencia | Quién o qué prueba | En el TP |
|---|---|---|
| Ninguna: quien programa | El mismo desarrollador | Los tests unitarios y de componentes se escriben junto con el código |
| Baja: otro integrante del equipo | Revisión del PR antes de mergear a `main` | **Pendiente:** hasta ahora los PR de `Pau` a `main` los mergeó quien trabaja en `Pau`. Es una mejora del proceso: pedir la aprobación de otro integrante en GitHub antes del merge |
| Media: herramientas que no conocen el código | Pipeline, SonarQube Cloud | Corren en cada push con las mismas reglas para todos; SonarQube encontró vulnerabilidades que los tests no buscaban |
| Alta: alguien de afuera | El docente en la defensa; el personal del local usando el panel | Usabilidad validada a mano con el personal; la demostración final |

Más independencia no es siempre mejor: el pipeline da feedback en minutos justamente porque no espera a un equipo
externo.

## Estimación y seguimiento

- **Estimación:** el plan del 20/10 estimó seis días (20 al 25/10). Se terminó en dos; el desvío y su lectura
  están en [04-metricas-y-analisis-estatico.md](04-metricas-y-analisis-estatico.md#métrica-de-proyecto).
- **Seguimiento:** cada ejecución del pipeline deja en su resumen la cobertura, el quality gate, los umbrales de
  carga y el reporte de Ruff; los defectos se siguen en Jira; las métricas se comparan contra la línea base en
  [alcance-medicion.md](alcance-medicion.md).

## Plantillas de caso y de defecto

Las dos plantillas, con un ejemplo cada una y los campos de trazabilidad (requisito, caso, defecto, test, commits),
están en [plantillas.md](plantillas.md). La de caso sigue los elementos del IEEE 829 (entradas y precondiciones,
resultado esperado, postcondiciones y dependencias).
