# Herramienta incorporada: SonarQube Cloud (SonarCloud)

Se incorporó con el proceso de cinco pasos: requisitos → mercado → prueba de concepto → matriz de decisión →
despliegue incremental. Proyecto: <https://sonarcloud.io/project/overview?id=pauliiortizz_OptiFull>.

## 1. Requisitos

Lo que tenía que resolver la herramienta, sacado de la consigna (quality gate del Nivel 3) y de cómo trabaja el
equipo:

| # | Requisito | Tipo |
|---|---|---|
| R1 | Analizar Python (API Flask, detección, caja) y JavaScript/JSX (panel React) | Obligatorio |
| R2 | Detectar bugs con severidad, duplicación y métricas de mantenibilidad (complejidad, deuda) | Obligatorio |
| R3 | Importar la cobertura que ya generan pytest-cov (XML) y Vitest (LCOV) | Obligatorio |
| R4 | Medir **código nuevo** por separado (la meta es 80 % de cobertura sobre código nuevo) | Obligatorio |
| R5 | Correr dentro de GitHub Actions y poder frenar el pipeline | Obligatorio |
| R6 | Costo cero (proyecto de tesis) | Obligatorio |
| R7 | Sin servidor propio que mantener (el único hosting es Render gratuito, 512 MB) | Deseable |
| R8 | Interfaz para revisar y justificar cada observación (falsos positivos con comentario) | Deseable |

## 2. Mercado

| Herramienta | Modelo | Qué ofrece | Limitación relevante para OptiFull |
|---|---|---|---|
| **SonarQube Cloud** | SaaS, gratis para repositorios públicos | Python + JS, bugs/vulnerabilidades/code smells, duplicación, cobertura importada, *new code period* | El plan gratuito trae un único quality gate fijo ("Sonar way") |
| SonarQube Community (self-hosted) | Gratis, se instala | Las mismas reglas base | Requiere un servidor con Java y base de datos (no entra en 512 MB); la edición Community analiza una sola rama |
| Codacy | SaaS, gratis para open source | Agrega varios linters, cobertura, gates por PR | Las métricas dependen de los linters que agrega; menos detalle de duplicación y deuda |
| DeepSource | SaaS, gratis para open source | Analizadores Python/JS, autofix, cobertura | Foco en PR; menos maduro para gates sobre "código nuevo" |

Además se evaluó seguir solo con **Ruff** (ya estaba): es rápido y bloquea errores probables, pero no mide
duplicación, no importa cobertura ni distingue código nuevo. Quedó como primer filtro dentro de build-test.

## 3. Prueba de concepto

Sobre la rama `Pau`, el 20/10/2026 (commit ef77d4e):

1. `sonar-project.properties` con el alcance de [alcance-medicion.md](alcance-medicion.md) (sin la copia de
   Ultralytics, que inflaba todo: se reemplazó por la dependencia en acb0c60).
2. Job `calidad` que sube el análisis con la cobertura de Python y del frontend.
3. Resultado del primer análisis: encontró un **bug real** que nadie había visto, `pdf.table(padding=...)` con
   `fpdf2>=2.7` → [DEF-001](defectos.md#def-001--fpdf227-acepta-versiones-que-rompen-el-pdf).
4. Se comprobó que la API (`/api/measures/component`, `/api/issues/search`) devuelve las medidas del análisis
   recién subido: eso permitió aplicar los umbrales de la consigna con un script propio, superando la
   limitación del gate fijo del plan gratuito.

Las otras tres herramientas se evaluaron con su documentación, sin prueba de concepto.

## 4. Matriz de decisión

Puntaje de 1 (no cumple) a 5 (cumple completo), ponderado por la importancia de cada criterio para el equipo.

| Criterio | Peso | SonarQube Cloud | SonarQube self-hosted | Codacy | DeepSource |
|---|---|---|---|---|---|
| R1 · Python + JS/JSX | 15 % | 5 | 5 | 4 | 4 |
| R2 · Bugs, duplicación, complejidad | 20 % | 5 | 5 | 3 | 4 |
| R3 + R4 · Cobertura y código nuevo | 20 % | 5 | 3 | 4 | 3 |
| R5 · GitHub Actions y bloqueo | 15 % | 4 (gate propio por API) | 3 | 4 | 4 |
| R6 · Costo | 10 % | 5 | 4 (gratis, pero hay que hostearlo) | 5 | 5 |
| R7 · Sin servidor que mantener | 10 % | 5 | 1 | 5 | 5 |
| R8 · Revisión y justificación de observaciones | 10 % | 5 | 5 | 4 | 4 |
| **Total ponderado** | 100 % | **4,85** | **3,80** | **4,00** | **4,00** |

Decisión: **SonarQube Cloud**. La diferencia está en R2 y R4: es la que mejor mide duplicación y separa el
código nuevo, que son dos de los tres umbrales del quality gate. Su única desventaja (gate fijo) se resolvió
con `.github/scripts/quality_gate.py`.

## 5. Despliegue incremental

| Etapa | Qué se hizo | Bloquea el pipeline |
|---|---|---|
| 1 | Ruff en build-test con reglas de errores probables (`E9`, `F`, `B`); se corrigieron las 31 observaciones | Sí (solo Ruff) |
| 2 | SonarQube Cloud en el job `calidad`, solo en `main` (el plan gratuito analiza la rama principal), con el gate "Sonar way" informativo | No |
| 3 | Cobertura de Python (sentencia + decisión) y del frontend importadas al análisis | No |
| 4 | `quality_gate.py`: bugs críticos = 0, duplicación ≤ 5 %, cobertura sobre código nuevo ≥ 80 % | **Sí**: si no se cumple, no hay deploy a QA |
| 5 | Revisión de las observaciones: DEF-001 corregido, sus dos líneas marcadas como falso positivo con justificación | — |

Estado al 20/10/2026 (último análisis de `main`, ae717d3): gate **OK**, cobertura total 72,1 %, cobertura sobre
código nuevo 94,2 %, duplicación 0,9 %, 15 bugs abiertos, ninguno crítico: 12 menores (elementos con `onClick`
sin manejo de teclado en el frontend) y 3 mayores (una comparación de floats en `video_source.py`, una promesa
sin `.catch` en `SectionPages.jsx` y una propiedad `border` duplicada en `PagesHeatmapCameras.jsx`). Ese
análisis es anterior a los tests de la caja y del frontend: los números se actualizan con el próximo push a `main`.
