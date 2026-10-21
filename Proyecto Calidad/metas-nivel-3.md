# Metas de calidad: Nivel 3 (prototipo avanzado)

Cada aspecto de la tabla de metas de la consigna, contra lo exigido para el Nivel 3, con su evidencia. Números de
SonarQube Cloud: análisis de `main` 6b5f0f3 (21/10/2026), carpeta `frontend/`.

| Aspecto | Exigido para el Nivel 3 | Estado | Evidencia |
|---|---|---|---|
| **Pipeline** | Compilación, pruebas, análisis estático, cobertura, quality gate y reporte automático | ✅ Cumplida | `.github/workflows/pipeline.yml`: build-test (compila, Ruff, tests, cobertura), calidad (SonarQube Cloud + gate), resúmenes y artefactos en cada ejecución |
| **Quality gate** | Bloquea ante bugs críticos, duplicación mayor a 5 % y cobertura sobre código nuevo menor al 80 % | ✅ Cumplida | `.github/scripts/quality_gate.py`. Bloqueó dos veces: [39461226443](https://github.com/pauliiortizz/OptiFull/actions/runs/39461226443) y [39495492793](https://github.com/pauliiortizz/OptiFull/actions/runs/39495492793). Hoy en OK |
| **Cobertura sobre código nuevo** | 80 % | ✅ Cumplida | 86,5 % |
| **Cobertura mínima sobre el código existente** | 80 % | ✅ Cumplida | Módulo web 94,5 % (API 98,0 %, panel 91,6 %) |
| **Plan de pruebas y riesgos** | Plan versionado con criterios de entrada y salida, riesgos priorizados por probabilidad × impacto y trazabilidad requisito → caso → defecto | ✅ Cumplida | [plan-de-pruebas.md](plan-de-pruebas.md) v3.0 (secciones 4, 5 y 8) |
| **Defectos** | Registrados con pasos, esperado y obtenido, vinculados a su caso de prueba en Jira u otra herramienta | ✅ Cumplida | [defectos.md](defectos.md) y Jira, proyecto [KAN](https://optifull.atlassian.net/issues?jql=project%3DKAN%20ORDER%20BY%20key%20ASC): 20 del módulo, cada uno con su test de regresión |
| **Herramienta nueva** | Incorporada con el proceso de cinco pasos | ✅ Cumplida | [herramienta-sonarcloud.md](herramienta-sonarcloud.md) |
| **Smoke test** | Ejecutado por el pipeline tras el despliegue | ✅ Cumplida | `pytest -m smoke` tras el deploy a QA (integration-qa) y a producción (deploy-prod) |
| **Integración externa** | Flujo E2E automatizado en cada despliegue | ✅ Cumplida, con una limitación | `test/e2e/` en el job e2e-qa, contra Render y Supabase. Con la cuenta de QA actual (empleado) recorre Productos y Alertas; el recorrido del administrador (Dashboard y Reportes) se probó localmente pero no en QA |
| **Stress y esfuerzo sostenido** | Stress ejecutado, con resultados y umbrales | ✅ Cumplida | Job carga-qa: stress (p95 2,4 s, umbral 5 s) y sostenida (p95 140 ms, umbral 2 s), con reportes HTML y CSV ([pruebas-de-carga.md](pruebas-de-carga.md)) |

**Las 10 metas del Nivel 3 se cumplen.**

## Lo que no se cumplió o quedó parcial

| Qué | Por qué | Qué haría falta |
|---|---|---|
| El E2E del administrador no corre contra QA | La cuenta del pipeline (`QA_USUARIO`) es de empleado | Crear una cuenta de administrador para QA con `db/crear_usuario.py --rol administrador` y cargarla en los secrets |
| Objetivo U4: todo se puede usar con teclado | Quedan 11 observaciones de accesibilidad (S1082) en el panel | Hallazgo H1 de [04-metricas-y-analisis-estatico.md](04-metricas-y-analisis-estatico.md#hallazgos) |
| Objetivo O4: recuperar el verde de `main` en menos de un día | La primera vez tardó 26 h, porque había que escribir los tests | Ya se cumple: la serie de fallas del 21/10 se resolvió en 2 h |
| La complejidad del módulo no bajó | 8 funciones con complejidad ciclomática mayor a 10, sin refactorizar | Hallazgo H3 (`generar_pdf()`) |
| Riesgo R9: pedidos de demo en el disco de Render | Si el email falla, el pedido puede perderse en el siguiente deploy | Guardar los pedidos en Supabase (cambio de la tesis) |
| Revisión de los PR por otro integrante | Los PR los mergeó la misma persona que trabaja en la rama | Exigir una aprobación en GitHub antes del merge |
