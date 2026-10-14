# Seguimiento — Corrección de medio término (Haiku 5.5)

Archivo de corrección: `informe/PI - 26 - OptiFULL - ..._correccion_mt_haiku-5.5.md`
Informe comparado: `informe/Informe de Proyecto Integrador - Optifull - v2.1 - 2026.docx.pdf` (165 páginas)

Estados: ✅ resuelto · 🟡 parcial · ❌ pendiente · ❔ no se puede verificar desde el PDF

## Estado de las acciones prioritarias

| # | Prioridad | Acción | Estado | Qué falta en el informe actual |
|---|---|---|---|---|
| 1 | Crítico | Bibliografía APA 7 + citas en el texto + fuente de Figuras 1 a 4 | 🟡 | Hecho (revisión del 14/10): fuente de las Figuras 1 a 4, instrucciones y ejemplo de Laudon borrados, y las 7 citas de Presentación, Diagnóstico y MT 1.4 a 2.3. Falta: las 5 marcas ⚠️ de la lista, la URL exacta del informe de la NRF y las citas de la sección 4 y de la Propuesta (tabla 1.a desde 4.1.1). |
| 2 | Crítico | Sacar la solución propia del Marco Teórico (2.4, 3.5, 3.6, 4.3.6) | ✅ | Hecho (revisión del 14/10). Detalles: en 3.5 queda "este enfoque permite" (pasar a "permitiría") y el índice todavía muestra el título viejo de 3.6. Lo que sigue en esta celda es el estado anterior: | Siguen igual: "La propuesta tecnológica plantea reutilizar" (2.4), "la propuesta consiste en utilizar las mismas imágenes" (3.5), "La propuesta de OptiFull busca posicionarse" y "poco explorado" (3.6), "El modelo conceptual de implementación se basa en el consumo de su API paga" (4.3.6). |
| 3 | Crítico | Fuente o eliminación de datos sin respaldo | ❌ | Siguen sin fuente: "menos del 10% de las franquicias" (Diagnóstico), "Diversos estudios" (1.6), "$0 USD" y "$15 USD" (4.6), "20 como límite" (4.3.4), "baja tasa de alucinación" (4.3.6), "YPF constituye una de las principales" (1.1), "La mayoría de los establecimientos" (1.4). |
| 4 | Crítico | Borrar instrucciones de la plantilla y texto dirigido al asistente | 🟡 | Ya no están las instrucciones del Abstract, de la Presentación, del Diagnóstico ni del Marco Teórico, ni la línea "Al final de la sección 2.11". Quedan "DEFINICIONES GENERALES…" (págs. 2 a 4 y su entrada en el índice), el título "EJEMPLO DE PORTADA", el "(opcional - recomendada)" del título de la tabla de trazabilidad, las instrucciones de Bibliografía y, en Pruebas, "Después va la tabla que te pasé antes… Eso no cambia." y "Plan de pruebas: se recomienda documentar aquí… (sección 22)". |
| 5 | Importante | Objetivos específicos con criterio medible | ❌ | Los 9 objetivos siguen siendo verbos de acción sin métrica. |
| 6 | Importante | Tabla de trazabilidad | ✅ | Tabla 1 completa. Detalle: quitar "(opcional - recomendada)" del título (va con el punto 4). |
| 7 | Importante | Figuras 1 a 4: mención previa, fuente y privacidad | ❌ | "Como se puede observar en las figuras 1, 2, 3 y 4" sigue después de las figuras; "Fuente: Hik-Connect"; "desde un ángulo superior el frente de la caja"; "Camara" sin tilde. La privacidad (personas visibles) no se puede verificar desde el texto. |
| 8 | Importante | Sección 3 con productos concretos | ✅ | Hikvision, Veesion, RetailNext, Sensormatic, Trax y Everseen con cita, más la Tabla 3. |
| 9 | Importante | Glosario | 🟡 | "Enrique" corregido, "Merma" agregada y orden alfabético correcto. Falta "Descuadre". Siguen los términos genéricos API, Flask, React, Supabase y LLM (y ahora también FastAPI, Expo Go, PyTorch y otros). |
| 10 | Importante | Unificar la denominación del trabajo y completar la fecha de la portada | ❌ | "Trabajo Final de Carrera" en 2.7. Fecha "<dia> de Febrero de 2027". |
| 11 | Importante | 2.5: fecha, cantidad de entrevistados y guía; gerencia o encargada | 🟡 | Resuelto con la Tabla 2 (visitas con fecha) y el Anexo A (entrevistados y guía). Falta unificar: 2.8 dice "la gerente de la tienda y los propietarios" y después "Según detalló la encargada" (2.8 y 2.9). |
| 12 | Menor | Redacción puntual | 🟡 | "Características:" resuelto. Siguen "a ojo", "aliado directo" y RTSP sin explicar en el Resumen. El "###" vacío no se puede verificar desde el PDF. |
| 13 | Menor | Jerarquía de encabezados del MT e índice | 🟡 | Índice actualizado con 4.x. Jerarquía de estilos ❔ (revisar en Google Docs). |
| 14 | Menor | Grafía "Blasón" y render de imágenes | ✅ | "Blasón" consistente en todo el informe. Las imágenes se ven en el PDF. |

Fuera del alcance de esta corrección, pero vacías: Beneficios, Impacto económico, Impacto social, Impacto medioambiental y Conclusión todavía tienen solo el texto de la plantilla.

---

## Punto 1 — Citas y bibliografía

### 1.a Citas que faltan insertar en el texto (con Herramientas → Citas)

Lista sacada de la Parte 2 de `bibliografia_apa7.md`, comparada con el PDF actual. Las ya insertadas no figuran.

| Sección | Lugar | Cita a insertar |
|---|---|---|
| Presentación | 1.er párrafo, "El avance de las tecnologías basadas en Inteligencia Artificial…" | (Russell & Norvig, 2021) |
| Diagnóstico → Impacto | párrafo de diferencias de stock "…o pérdidas ocasionadas por hurtos." | (National Retail Federation, 2023) |
| 1.4 | "…los avances tecnológicos han ampliado significativamente las posibilidades…" | (Szeliski, 2022) |
| 1.6 | "Diversos estudios relacionados con el sector retail destacan…" | (National Retail Federation, 2023; Underhill, 2009) |
| 2.2 | "…metodologías de ingeniería de software incluyen actividades de relevamiento…" | (Sommerville, 2016; Pressman & Maxim, 2020) |
| 2.3 | párrafos de entrevistas y observación directa | (Hernández Sampieri & Mendoza Torres, 2018) |
| 4.1.1 | VS Code, 1.er párrafo | (Visual Studio Code, s. f.) |
| 4.2.1 | Expo Go, 1.er párrafo | (Expo, s. f.) |
| 4.3.1 | "YOLOv8 representa una de las evoluciones…" | (Redmon et al., 2016; Jocher et al., 2023) |
| 4.3.1 | Licenciamiento restrictivo | (Ultralytics, s. f.) |
| 4.3.2 | "Gemma es una familia de modelos abiertos…" | (Gemma Team, 2024) |
| 4.3.2 | Ajuste fino (LoRA) | (Hu et al., 2021) |
| 4.3.3 | Roboflow, 1.er párrafo | (Roboflow, s. f.) |
| 4.3.4 | Límite de consumo | (Google, s. f.) |
| 4.3.5 | Groq, 1.er párrafo | (Groq, s. f.) |
| 4.3.6 | Claude API, 1.er párrafo | (Anthropic, s. f.) |
| 4.3.10 | después de "se analizó RapidFuzz" | (Bachmann, s. f.) |
| 4.5.1.1 | NumPy y OpenCV | (Harris et al., 2020; Bradski, 2000) |
| 4.5.1.2 | SciPy | (Virtanen et al., 2020) |
| 4.5.2.1 | Ultralytics Solutions | (Jocher et al., 2023) |
| 4.5.3.1 | Plotly | (Plotly Technologies, s. f.) |
| 4.6.1 | Supabase, cuotas de 500 MB y 1 GB | (Supabase, s. f.) |
| 4.7.1 | MediaMTX | (bluenviron, s. f.) |
| 4.7.2 | "…construido sobre el protocolo WireGuard" | (Tailscale, s. f.; Donenfeld, 2017) |
| 4.7.3 | AnyDesk y TeamViewer | (AnyDesk Software GmbH, s. f.; TeamViewer, s. f.) |
| 4.7.4 | "…objetivos frecuentes de ataques automatizados" | (Antonakakis et al., 2017) |
| 4.7.4 | "…si el proveedor de internet aplica CGNAT…" | (Perreault et al., 2013) |
| 4.7.5 | FFmpeg | (FFmpeg, s. f.) |
| 4.8.1 | "…integración nativa con librerías críticas como PyTorch…" | (Paszke et al., 2019) |
| 4.8.1 | Flask | (Pallets, s. f.) |
| 4.8.2 | React / Angular / Vite | (Meta Open Source, s. f.) / (Angular, s. f.) / (Vite, s. f.) |
| 4.9 | Docker, Render, GitHub Actions | (Docker Inc., s. f.), (Render, s. f.), (GitHub, s. f.) |
| Propuesta | Historias de usuario | (Cohn, 2004) |
| Propuesta | Patrones de diseño (intro) | (Gamma et al., 1994) |
| Propuesta | Base de datos compartida | (Hohpe & Woolf, 2003) |
| Propuesta | Repository | (Fowler, 2002) |
| Propuesta | Módulo 3, "…preentrenados sobre el conjunto de datos COCO" | (Lin et al., 2014) |
| Propuesta | Módulo 9, Matplotlib | (Hunter, 2007) |

Regla de control: si una referencia de la lista no se cita en ningún lugar, se borra de la lista (y viceversa).

### 1.b Limpieza de la sección Bibliografía

1. Borrar todo el texto de instrucciones, desde "En esta sección se deben incluir todas las fuentes…" hasta "●​ Documentación técnica.", incluido el ejemplo de Laudon & Laudon (cuenta como cita y referencia que no existen).
2. Borrar las 5 marcas ⚠️. Antes, abrir esas URL (Anthropic, Google Gemini, Groq, Ultralytics y NRF) y confirmar que funcionan.
3. Idealmente, regenerar la lista con "Insertar bibliografía" de Google Docs en lugar de dejarla pegada a mano: la plantilla lo exige.

### 1.c Fuente de las Figuras 1 a 4

Las capturas son de las cámaras del propio local, obtenidas por el equipo con la aplicación, así que no son material de un tercero. Reemplazar en las cuatro figuras:

> Fuente: Hik-Connect

por:

> Fuente: elaboración propia a partir de capturas de la aplicación Hik-Connect.
