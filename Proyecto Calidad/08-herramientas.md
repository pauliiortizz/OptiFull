# 8 · Herramientas del ecosistema

## Mapa de herramientas

Con las categorías del mapa del ecosistema de la clase del 28/09. Ninguna herramienta lo hace todo: cada una cubre
una parte del ciclo.

| Categoría | Qué resuelve | Qué usa el TP | Por qué esa y no otra |
|---|---|---|---|
| **Gestión de pruebas y defectos** | Planificar, organizar y trazar | **Jira** (proyecto KAN) para los defectos; el plan y la trazabilidad, versionados en el repositorio | Jira es la que pide la consigna; el plan vive junto al código para que cada cambio de umbral quede en el mismo commit |
| **Análisis estático** | Revisar el código sin ejecutarlo | **SonarQube Cloud** (con el quality gate), **Ruff** (Python) y **oxlint** (JavaScript) | SonarQube Cloud: ver los cinco pasos más abajo. Ruff y oxlint son rápidos y corren en cada push, antes de los tests |
| **Diseño / BDD** | Especificar el comportamiento esperado | No se usa (Cucumber o similares) | Los requisitos ya están escritos en la tesis (RF/RNF) y la trazabilidad va directo a los tests; un BDD agregaría una capa que el equipo no necesita para un módulo de este tamaño |
| **Ejecución y registro** | Automatizar y correr pruebas | **pytest** (API), **Vitest + Testing Library** (panel), **Playwright** (E2E), **requests** (API por HTTP, el papel de Postman/Newman) | pytest y Vitest son los de cada lenguaje del módulo; Playwright, frente a Selenium o Cypress, maneja solo las esperas y graba trazas que se pueden abrir después de una falla en el CI |
| **Cobertura** | Medir qué código ejecutan las pruebas | **pytest-cov** (sentencia y decisión) y **V8** en Vitest | Generan los reportes XML y LCOV que importa SonarQube Cloud |
| **Rendimiento** | Medir carga, estrés y escalabilidad | **Locust** | Frente a JMeter o Gatling: los escenarios se escriben en Python (el mismo lenguaje del backend y de las demás pruebas) y genera reportes HTML con gráficos y CSV que el pipeline publica |
| **CI/CD y despliegue** | Correr todo en cada cambio y desplegar | **GitHub Actions**, **Docker**, **Render** | GitHub Actions viene con el repositorio; la misma imagen Docker se prueba en CI y se despliega en QA y producción |
| **Pruebas específicas** | Dominios con protocolos propios | No aplica | El módulo web habla HTTP; las cámaras RTSP son del pipeline de video, fuera del TP |
| **Asistentes de IA** | Generar borradores de pruebas, revisar código | Asistente de IA para código (ver [uso-de-ia.md](uso-de-ia.md)) | Se usa como copiloto: lo que genera se revisa y se ejecuta antes de subirlo |

## Herramienta nueva: SonarQube Cloud, con el proceso de cinco pasos

El documento completo, con la matriz de decisión ponderada, está en
[herramienta-sonarcloud.md](herramienta-sonarcloud.md). En resumen:

| Paso | Qué se hizo |
|---|---|
| **1. Requisitos** | Analizar Python y JavaScript, medir bugs, duplicación y cobertura, separar el código nuevo, frenar el pipeline, costo cero y sin servidor propio |
| **2. Mercado** | SonarQube Cloud, SonarQube autoalojado, Codacy y DeepSource (lista corta) |
| **3. Prueba de concepto** | En la rama de trabajo, con el alcance definido; encontró un defecto real que nadie había visto (DEF-001, fpdf2) |
| **4. Matriz de decisión** | SonarQube Cloud 4,85 · Codacy 4,00 · DeepSource 4,00 · SonarQube autoalojado 3,80 (siete criterios ponderados) |
| **5. Despliegue incremental** | Primero Ruff bloqueante, después SonarQube informativo, después con cobertura, después el gate bloqueante, la revisión de las observaciones y la de las vulnerabilidades |

Su única desventaja (el plan gratuito trae un quality gate fijo) se resolvió con un script propio que aplica los
umbrales de la consigna (`.github/scripts/quality_gate.py`).

## Registro en Jira

Los defectos del TP están en Jira, proyecto **KAN**, importados desde [defectos-jira.csv](defectos-jira.csv): tipo
Error, con la prioridad según la severidad, las etiquetas `optifull-calidad` y `sev-<severidad>`, y en la
descripción los pasos, el resultado esperado y el obtenido, el test de regresión y los commits rojo y verde. Los 20
del módulo web y los 7 de los otros módulos están en estado Completado. La correspondencia con el registro del
repositorio está en [defectos.md](defectos.md) (por ejemplo, DEF-023 = KAN-45).

## Stress y esfuerzo sostenido

Con Locust, contra QA, en cada deploy a `main` (job `carga-qa`):

| Perfil | Carga | Umbrales | Último resultado |
|---|---|---|---|
| **Stress** | Escalones de 5 a 40 usuarios, 6 min | Errores ≤ 5 %, p95 ≤ 5 s, p99 ≤ 10 s | 0 %, 2,4 s, 9,4 s ✅ |
| **Esfuerzo sostenido** | 15 usuarios constantes, 10 min | Errores ≤ 1 %, p95 ≤ 2 s, p99 ≤ 5 s, degradación del p95 ≤ 2× | 0 %, 140 ms, 510 ms, 0,58 ✅ |

Escenario, umbrales justificados, resultados antes y después de la mejora y reportes en
[pruebas-de-carga.md](pruebas-de-carga.md).
