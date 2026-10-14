> **Modelo usado:** gpt-6.1-sol (codex)
> **Resultado orientativo / de referencia:** esta corrección fue generada automáticamente y puede contener errores. Verificar contra el documento original antes de usarla.

# Corrección de medio término — OptiFULL

## 1. Datos del documento

- Título: SISTEMA INTELIGENTE DE ANÁLISIS DE FLUJO Y OPTIMIZACIÓN OPERATIVA MEDIANTE COMPUTER VISION PARA TIENDAS FULL, OPTIFULL.
- Alumnos: Blasón, Agostina; Nahmias, Arnon Daniel; Ortiz Noseda, Paulina (EJEMPLO DE PORTADA).
- Directores: Juarez, Leandro; Porrini, Federico Eduardo; Carreño, Ignacio Luciano (EJEMPLO DE PORTADA).
- Secciones detectadas: Índice; DEFINICIONES GENERALES PARA CONFECCIÓN DEL INFORME DE PROYECTO INTEGRADOR (Redacción: Formal, Claro, Objetivo, Con citas y referencias; Formato; Imágenes / Diagramas; Uso de imágenes, figuras y diagramas); EJEMPLO DE PORTADA (Alumnos, Directores); RESUMEN - ABSTRACT (inglés y español); PRESENTACIÓN DEL TEMA; GLOSARIO; DIAGNÓSTICO (PROBLEMÁTICA) (Estado del arte, Impacto, Oportunidades); OBJETIVOS (GLOBAL, ESPECÍFICOS, TABLA DE TRAZABILIDAD); MARCO TEÓRICO; 1. Contexto General del Problema (1.1 Introducción, 1.2 Las tiendas FULL como entorno operativo, 1.3 Importancia del control operativo en comercios minoristas, 1.4 Sistemas de videovigilancia en comercios, 1.5 Procedimientos actuales del dominio, 1.6 Estudios y tendencias actuales, 1.7 Relevancia de la problemática); 2. Análisis de Campo (2.1 Introducción, 2.2 Importancia del análisis de campo en proyectos de ingeniería de software, 2.3 Técnicas de recolección de información, 2.4 Justificación del análisis de campo para el presente proyecto, 2.5 Planificación del proceso de relevamiento, 2.6 Objetivos del análisis de campo, 2.7 Aporte del análisis de campo al proyecto, 2.8 Hallazgos del Relevamiento Operativo y Reglas de Negocio, 2.9 Logística ante Picos de Flujo y Comportamiento de Clientes, 2.10 Infraestructura de Captura y Distribución de Cámaras, 2.11 Viabilidad Técnica de Conexión y Extracción de Footage); 3. Opciones Similares en el Mercado (3.1 Introducción, 3.2 Soluciones orientadas a la videovigilancia inteligente, 3.3 Plataformas de análisis para el sector retail, 3.4 Limitaciones de las soluciones existentes, 3.5 Oportunidad de innovación, 3.6 Comparación entre las soluciones existentes y la propuesta del proyecto); 4. Tecnologías Investigadas (4.1 Entornos de Desarrollo: Visual Studio Code; 4.2 Desarrollo y Pruebas en Entornos Móviles: Expo Go; 4.3 Tecnologías de Visión por Computadora e Inteligencia Artificial: YOLOv8, Gemma AI, Roboflow, Google Gemini API, Groq, Claude API; 4.4 Herramientas de Asistencia al Desarrollo y Documentación: GPT y Claude; 4.5 Análisis de tecnologías para Mapas de Calor: NumPy y OpenCV, SciPy, Ultralytics Solutions, Plotly, Cuadro Comparativo; 4.6 Tecnologías de Bases de Datos: Supabase, Soluciones de Bases de Datos Gestionadas; 4.7 Tecnologías de Conectividad Remota y Retransmisión de Video: MediaMTX, Tailscale, AnyDesk y TeamViewer, DNS Dinámico; 4.8 Análisis Comparativo de Tecnologías de Desarrollo: Python vs. Node.js, React, Vue y Angular); PROPUESTA DE SOLUCIÓN (Aspectos clave a incluir, Alcance Funcional, Diseño, Implementación, Pruebas); BENEFICIOS POST-IMPLEMENTACIÓN; IMPACTO ECONÓMICO; IMPACTO SOCIAL; IMPACTO MEDIOAMBIENTAL; CONCLUSIÓN; BIBLIOGRAFÍA / REFERENCIAS; ANEXOS (Pasos para acceder a las NVRs y exportar las grabaciones, Configuración del nodo de captura remota).
- Alcance real del documento: leído completo hasta ANEXOS, incluida la verificación desde un equipo remoto; el MT termina en 4.8.2. Se evalúan únicamente estructura hasta el MT, citas/referencias y contaminación del MT; no se penalizan secciones posteriores.

## 2. Veredicto

**REQUIERE CORRECCIÓN** — Contaminación parcial del MT: "La propuesta de OptiFull busca posicionarse como una alternativa" (3.6). Hay datos centrales sin fuente: "menos del 10% de las franquicias" (Diagnóstico), y bibliografía propia no encontrada.

## 3. Estructura

| Sección | Presente | Estado | Observación (con evidencia) |
|---|---|---|---|
| Portada | SÍ | Incompleto | Incluye institución, facultad, proyecto, alumnos, directores, "Informe Final de Grado" y "Córdoba - Argentina" (EJEMPLO DE PORTADA); completar el día: "<dia>" (misma sección). |
| Resumen + Abstract | SÍ | Completo | Español primero, inglés fiel después, ambos bajo 300 palabras y con los componentes requeridos: "Los resultados obtenidos demuestran la viabilidad técnica" (Resumen). Observar jerga sin explicar: "flujos de video RTSP" (Resumen). |
| Presentación del Tema | SÍ | Completo | Expone tema, relevancia, contexto y propósito: "desarrollar una plataforma de software basada en Visión por Computadora" (PRESENTACIÓN DEL TEMA). |
| Glosario | SÍ | Incompleto | Tiene dominio, como "Planograma" (GLOSARIO), pero incluye genéricos: "API (Application Programming Interface)" y "DOM Virtual (Virtual Document Object Model)" (GLOSARIO); depurar. |
| Diagnóstico | SÍ | Completo | Incluye "Estado del arte (contexto actual)", "Impacto" y "Oportunidades" (DIAGNÓSTICO); corregir su sustento documental, detallado abajo. |
| Objetivos | SÍ | Incompleto | Global coherente con el diagnóstico; específicos concretos, pero sin criterios de aceptación: "Generar mapas de calor, métricas de flujo y estimaciones de tiempos de espera en caja" (ESPECÍFICOS). |
| Tabla de trazabilidad (opcional) | SÍ | Placeholder | Solo conserva la instrucción "Objetivo específico → evidencia de cumplimiento" (TABLA DE TRAZABILIDAD); tabla real no encontrada. Sugerirla como mejora opcional. |
| Marco Teórico | SÍ | Incompleto | Desarrolla contexto, campo y tecnologías con pros/contras, pero no identifica estudios concretos: "Diversos estudios relacionados con el sector retail" (1.6); mezcla investigación y solución propia (ver sección 5). |

Otros hallazgos de estructura/formato:

- Corregir restos de plantilla hasta el MT: "Aspectos clave a Incluir en el MT" (MARCO TEÓRICO) y "En esta sección se introduce de manera general el tema del proyecto" (PRESENTACIÓN DEL TEMA); retirar instrucciones y ejemplos editoriales.
- Corregir nota editorial incrustada: "Va con el mismo formato que los dos puntos anteriores" (2.11 Viabilidad Técnica de Conexión y Extracción de Footage).
- Corregir coloquialismo: "verificar los faltantes a ojo" (DIAGNÓSTICO, Estado del arte); reemplazar por una descripción formal del control visual.
- Observar errata: "fotograma de video Enrique" (GLOSARIO, Inferencia); revisar el término final.
- Observar hilo conductor: "tiempos de espera en caja" (ESPECÍFICOS) frente a "principalmente en la entrega de pedidos ya abonados" (DIAGNÓSTICO, Impacto); justificar la métrica elegida ante el cuello de botella descrito.
- Corregir comparación de mercado genérica: "una gran parte de estas soluciones se encuentra orientada a grandes cadenas comerciales" (3.3); alternativas comerciales identificadas por nombre y contrastadas con fuentes, no encontrado.
- Corregir mención tardía de figuras 1–4: "Como se puede observar en las figuras 1, 2, 3 y 4" (DIAGNÓSTICO) aparece después de las cuatro imágenes; introducirlas antes. Tienen número, descripción y texto alternativo en el Markdown.
- Observar imagen de portada: "![](data:image/png;base64...)" (EJEMPLO DE PORTADA); texto alternativo no encontrado en el Markdown. Verificar en el original si es un logotipo institucional y agregar identificación accesible.
- Observar formato visual: "El único formato exigido es el justificado" (DEFINICIONES GENERALES, Formato); la justificación y los metadatos originales de imágenes no son verificables en esta exportación Markdown.

## 4. Citas y referencias

- Total de citas en texto: 0 del trabajo — Total de entradas en bibliografía: 0 del trabajo; existe 1 cita y 1 referencia didácticas, ambas expresamente bajo "Ejemplo:" (BIBLIOGRAFÍA / REFERENCIAS).
- ¿APA v7?: NO — Bibliografía propia no encontrada; "La bibliografía debe realizarse utilizando norma APA v7" (BIBLIOGRAFÍA / REFERENCIAS) es una instrucción conservada, no una bibliografía elaborada. No es una lista de links pelados.
- 3a. Citas APA únicas del trabajo: no encontrado. Única muestra literal: "(Laudon & Laudon, 2020)" (BIBLIOGRAFÍA / REFERENCIAS, ejemplo); no se considera fuente utilizada por el proyecto.
- 3b. Entradas del trabajo: no encontrado. Única muestra: "Laudon, K. C., & Laudon, J. P. (2020). Sistemas de información gerencial. Pearson." (BIBLIOGRAFÍA / REFERENCIAS, ejemplo); total de muestras: 1.
- 3c. Cruce en ambos sentidos: no encontrado un par cita↔referencia del trabajo; el par de Laudon pertenece únicamente al ejemplo de plantilla.

| Problema | Detalle (con evidencia) | Gravedad |
|---|---|---|
| Cita sin referencia | Citas APA del trabajo: no encontrado. Hay atribución mediante hipervínculo a "Hikvision" (GLOSARIO, Hik-Connect), sin autor-fecha ni entrada completa en BIBLIOGRAFÍA / REFERENCIAS. | Media |
| Referencia sin cita | Entradas propias: no encontrado; no imputar al proyecto la muestra "Laudon, K. C., & Laudon, J. P. (2020)" (BIBLIOGRAFÍA / REFERENCIAS). | Baja |
| Dato sin fuente | "menos del 10% de las franquicias" (DIAGNÓSTICO): fuente, universo, fecha y método no encontrado en el documento completo. | Alta |
| Dato sin fuente | "Diversos estudios relacionados con el sector retail destacan la creciente adopción" (MT, 1.6): estudios identificados y citados, no encontrado. | Alta |
| Dato sin fuente | "su implementación suele representar un costo elevado" (MT, 3.3): no hay productos, precios ni estudios que sustenten la limitación central del mercado. | Alta |
| Dato sin fuente | "solicitudes diarias, teniendo 20 como límite" (MT, 4.3.4 Google Gemini API): fuente, modelo, plan y fecha de consulta, no encontrado. | Media |
| Dato sin fuente | "$15 USD mensuales" (MT, 4.6.2): fuente y configuración del servicio que sustenten el costo comparado, no encontrado. | Media |
| Otro (figura sin fuente completa) | "Fuente: Hik-Connect" (DIAGNÓSTICO, figuras 1–4) identifica una aplicación; autoría de las capturas y referencia completa no encontrado. Aclarar elaboración propia mediante la aplicación o, si son ajenas, autor y referencia. | Media |
| Otro (relevamiento sin identificación suficiente) | "La entrevista con la gerencia" (MT, 2.8): fecha y registro de entrevista, no encontrado; documentar el relevamiento y atribuir los datos del diagnóstico. | Media |

- URLs con tracking: no encontrado en todo el documento; el enlace "Hikvision" (GLOSARIO, Hik-Connect) no presenta esos parámetros.
- Fuentes débiles como única evidencia de un dato central: no encontrado; "Hikvision" (GLOSARIO) es un enlace comercial sobre su aplicación, no sustenta el diagnóstico ni las comparaciones de mercado.

## 5. Contaminación del Marco Teórico

**Resultado:** PARCIAL

- 2.4 Justificación del análisis de campo para el presente proyecto — "La propuesta tecnológica plantea reutilizar la infraestructura de videovigilancia existente" — anticipa la solución propia; conservar la justificación del relevamiento y trasladar esta formulación de propuesta.
- 3.5 Oportunidad de innovación — "la propuesta consiste en utilizar las mismas imágenes para asistir al personal en tareas operativas" — formula el enfoque de la solución en lugar de cerrar una comparación neutral.
- 3.6 Comparación entre las soluciones existentes y la propuesta del proyecto — "La propuesta de OptiFull busca posicionarse como una alternativa" — presenta y defiende el sistema propio dentro del MT; trasladar esa comparación con la propuesta a la sección correspondiente.
- 4.3.6 Claude API (Anthropic) — "el pipeline de visión por computadora envía resúmenes estructurados o datos visuales" — desarrolla un flujo de integración propio con prompts y consumo por la lógica de negocio; sustituir por evaluación general de capacidades y límites con fuentes.

## 6. Acciones prioritarias

- **Crítico:** Trasladar la solución propia fuera del MT: "La propuesta de OptiFull busca posicionarse como una alternativa" (3.6); conservar investigación comparativa neutral y documentada.
- **Crítico:** Sustentar o retirar la cifra "menos del 10% de las franquicias" (DIAGNÓSTICO); construir citas y referencias reales, pues "Laudon, K. C., & Laudon, J. P. (2020)" (BIBLIOGRAFÍA / REFERENCIAS) es solo un ejemplo.
- **Importante:** Identificar productos y estudios, respaldar comparaciones y documentar el campo: "La entrevista con la gerencia" (2.8); definir métricas y umbrales para "Generar mapas de calor" (ESPECÍFICOS).
- **Importante:** Depurar instrucciones y términos genéricos: "Aspectos clave a Incluir en el MT" (MARCO TEÓRICO), "API (Application Programming Interface)" (GLOSARIO); anticipar la mención "figuras 1, 2, 3 y 4" (DIAGNÓSTICO) y aclarar su autoría.
- **Menor:** Completar "<dia>" (EJEMPLO DE PORTADA), revisar "video Enrique" (GLOSARIO) y considerar completar la tabla opcional "Objetivo específico → evidencia de cumplimiento" (TABLA DE TRAZABILIDAD).
