# Uso de IA en el TP

La consigna permite usar IA para generar pruebas, scripts o texto, siempre que el grupo entienda, ejecute y pueda
explicar todo lo entregado. Lo usamos como en la clase del 05/10: **potenciación, no reemplazo**. El asistente
propone un primer borrador y el equipo decide, corrige y valida.

## Para qué se usó

| Tarea | Qué hizo el asistente | Qué hizo el equipo |
|---|---|---|
| Tests unitarios y de componentes | Borradores de casos, incluidos casos límite (vacíos, nulos, respuestas de error) | Revisar que cada test verifique el comportamiento esperado por el negocio, ejecutarlos y ver cada regresión en rojo antes del arreglo |
| Scripts de pipeline y de carga | Borradores del E2E (Playwright), de los perfiles de Locust y del verificador de umbrales | Fijar los umbrales, correr las pruebas localmente y contra QA, y leer cada falla del pipeline |
| Revisión de las vulnerabilidades de SonarQube Cloud | Análisis de cada observación y una prueba para cada una | Decidir cuáles eran reales y cuáles se justifican, y marcarlas en SonarQube Cloud |
| Documentación | Borradores de estos documentos a partir de los datos del pipeline, de SonarQube Cloud y de Jira | Revisar que cada número coincida con la herramienta de donde sale |

## Reglas que seguimos

1. **Nada se sube sin ejecutarlo.** Cada cambio pasó por la suite local y por el pipeline.
2. **Primero el test que falla.** Para cada defecto, el test de regresión se vio en rojo antes del arreglo; un test
   generado que pasa de entrada no prueba nada.
3. **Los números salen de la herramienta, no del asistente.** Cobertura, duplicación, tiempos de carga y estados de
   Jira se copian del pipeline, de SonarQube Cloud y de Jira.
4. **Las decisiones son del equipo:** qué módulo medir, qué umbrales usar, qué vulnerabilidades aceptar.

## Errores del asistente que el proceso detectó

Los mismos controles que usamos para el producto detectaron errores en lo que proponía el asistente:

| Qué propuso | Qué lo detectó | Qué se hizo |
|---|---|---|
| Un E2E que suponía una cuenta de administrador | El E2E falló en QA ([39639347637](https://github.com/pauliiortizz/OptiFull/actions/runs/39639347637)) | El test lee el rol de la respuesta del login y recorre lo que corresponde |
| Subir los hilos de gunicorn para resolver el stress | La prueba de carga no mejoró (p95 de 7,6 s a 8,2 s) | Se descartó con datos y se buscó la causa real: la conexión por pedido |
| Verificar el logout sin esperar la respuesta del servidor | El E2E falló en QA por una carrera ([39654144684](https://github.com/pauliiortizz/OptiFull/actions/runs/39654144684)) | El test espera la respuesta de `/api/logout` |
| Métricas y afirmaciones de los documentos | Revisión contra SonarQube Cloud, git y los tests | Se corrigieron antes de entregar |

Por eso la IA no reemplaza al proceso de calidad: es una fuente más de cambios que el proceso tiene que verificar.
