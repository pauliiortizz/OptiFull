> **Modelo usado:** Haiku 5.5
> **Resultado orientativo / de referencia:** esta corrección fue generada automáticamente y puede contener errores. Verificar contra el documento original antes de usarla.

# Corrección de medio término — OptiFULL

## 1. Datos del documento
- Título: "SISTEMA INTELIGENTE DE ANÁLISIS DE FLUJO Y OPTIMIZACIÓN OPERATIVA MEDIANTE COMPUTER VISION PARA TIENDAS FULL, OPTIFULL" (Portada)
- Alumnos: Blasón, Agostina; Nahmias, Arnon Daniel; Ortiz Noseda, Paulina
- Directores: Juarez, Leandro; Porrini, Federico Eduardo; Carreño, Ignacio Luciano
- Secciones detectadas: Índice; Definiciones generales (texto de plantilla); Portada; Resumen-Abstract; Presentación del tema; Glosario; Diagnóstico (Problemática); Objetivos (Global, Específicos); Tabla de trazabilidad; Marco Teórico (1. Contexto General del Problema; 2. Análisis de Campo; 3. Opciones Similares en el Mercado; 4. Tecnologías Investigadas, 4.1 a 4.8); Propuesta de solución; Beneficios; Impacto económico; Impacto social; Impacto medioambiental; Conclusión; Bibliografía / Referencias; Anexos.
- Alcance real del documento: el archivo tiene 1769 líneas. El Marco Teórico va de la línea 468 a la 1063 (cierra en "4.8 Análisis Comparativo de Tecnologías de Desarrollo"). Desde "PROPUESTA DE SOLUCIÓN" (línea 1064) en adelante no se evalúa estructura ni contenido, salvo la Bibliografía, que entra en el Paso 3.

## 2. Veredicto
**REQUIERE CORRECCIÓN** — La bibliografía está vacía (0 entradas) y el texto no tiene ninguna cita en formato APA; hay datos centrales sin fuente y el Marco Teórico describe la solución propia ("La propuesta de OptiFull busca posicionarse", línea 785). Además quedan bloques de instrucciones de la plantilla.

## 3. Estructura
| Sección | Presente | Estado | Observación (con evidencia) |
|---|---|---|---|
| Portada | SÍ | Incompleto | Fecha sin completar: "*<dia>* de Febrero de 2027" (201). Título de plantilla: "EJEMPLO DE PORTADA" (177). UCC, Facultad de Ingeniería, "Informe Final de Grado", alumnos, directores y "Córdoba - Argentina" presentes. |
| Resumen + Abstract | SÍ | Completo | Español primero, inglés después. Extensión estimada ≈250 palabras (≤300). Cubre introducción, problema, solución y resultados. Residuo de plantilla: "El Abstract es un resumen breve y conciso" (209). |
| Presentación del Tema | SÍ | Completo | Tema, relevancia y propósito presentes ("el propósito central de este proyecto integrador consiste en desarrollar"). Residuos: "Es clave establecer claramente el propósito" (250) y "Nota:" (252). |
| Glosario | SÍ | Completo (requiere ajustes) | Incluye términos genéricos que la plantilla excluye: "API (Application Programming Interface)" (274), "Flask:" (308), "React:" (344), "Supabase:" (356). Error: "...de video Enrique" (316). Orden alfabético roto: "PyTorch:" (318) antes de "IP (Internet Protocol)" (320). |
| Diagnóstico | SÍ | Completo | Estado del arte (384), Impacto (414) y Oportunidades (424) presentes. Instrucciones de plantilla sin borrar: "En esta sección se presenta detalladamente" (370). |
| Objetivos | SÍ | Incompleto | Global presente: "Desarrollar una solución basada en Visión por Computadora" (444). Específicos sin criterio medible (ver Paso 3 y Acciones). Ejemplos de plantilla: "Implementar un algoritmo de IA para predecir el stock" (450). |
| Tabla de trazabilidad | SÍ (solo instrucción) | Vacío / Placeholder | Solo aparece la consigna: "Objetivo específico → evidencia de cumplimiento" (466). No hay tabla. Es opcional, pero se recomienda completarla. |
| Marco Teórico | SÍ | Completo con residuos y contaminación | Las cuatro áreas de la plantilla están presentes (1 a 4). Consignas sin borrar: "El Marco Teórico (MT) proporciona el" (470) y "Aspectos clave a Incluir en el MT" (476). Contaminación PARCIAL (Paso 4). |

Otros hallazgos de estructura/formato:
- Bloques de instrucciones de plantilla a eliminar (líneas): 127-175 ("DEFINICIONES GENERALES PARA CONFECCIÓN DEL INFORME"), 177, 209-222, 250-254, 272, 370-378, 438-450, 464-466, 470-494. Incluye también la entrada del índice (línea 3).
- Texto dirigido a un asistente dentro del MT: "Al final de la sección 2.11, después del punto" (703).
- Índice desactualizado: la última entrada de la sección 4 es "4.3.3 Roboflow 43" (95); no figuran 4.3.4 a 4.3.6 ni 4.5 a 4.8.
- Encabezados inconsistentes en el MT: "2. Análisis de Campo" como H1 (593), "1. Contexto General del Problema" en negrita (496), "4.1 Entornos de Desarrollo" como H3 (795) y "4.5 Análisis de tecnologías para Mapas de Calor" en negrita (930).
- Encabezado vacío: "###" (1016), dentro de "4.6 Tecnologías de Bases de Datos".
- Terminología: "Trabajo Final de Carrera" (601, 665) no coincide con "Informe Final de Grado" de la portada (187).
- Grafía del apellido: portada "Blasón" (191); nombre del archivo "Blason". Observar y verificar.
- Abstract: "Características:" pegado a un ítem de lista (216); "flujos de video RTSP" sin explicar (230), lo que contradice "sin jerga"; "Los resultados obtenidos demuestran la viabilidad técnica" (232) no incluye ningún dato de resultado.
- Coloquialismos: "verificar los faltantes a ojo" (386); "se convierte en un aliado directo" (382).
- Diagnóstico: "Oportunidades" repite la idea de 426 en 428: "La infraestructura de cámaras ya instalada en la tienda representa la base tecnológica" (Observar, redundancia).
- Hilo conductor: el Diagnóstico describe mermas y descuadres: "dinero sobrante o mermas que no se facturan formalmente" (420) y "validar los descuadres de inventario al final de la jornada" (430). Ningún objetivo específico los cubre (Observar).
- Análisis de campo (2.5): "entrevistas semiestructuradas y observaciones presenciales" (639) sin fecha, cantidad de entrevistados ni guía de preguntas. Actores inconsistentes: "La entrevista con la gerencia" (675) frente a "Según detalló la encargada" (677) (Observar).
- Tabla 4.5.4: "Cuadro Comparativo de Tecnologías Investigadas de Mapas de Calor" (986) no tiene número ni fuente.
- Imágenes: el src aparece como "data:image/jpeg;base64..." (388, 394, 400, 406). Verificar que se visualizan en el archivo final.

Figuras (Diagnóstico, Figuras 1 a 4): número ✓, descripción ✓, texto alternativo ✓. Fallan dos puntos. (a) Mención previa ✗: "Como se puede observar en las figuras 1, 2, 3 y 4" (412) aparece después de las figuras (388-410). (b) Fuente ✗: "Fuente: Hik-Connect" no usa la forma exigida (elaboración propia / adaptado de / tomado de) y es un tercero sin referencia en bibliografía. Figura 4: "desde un ángulo superior el frente de la caja" (408), falta una preposición. Observar privacidad: las fotos muestran "clientes y personal" (388), y el proyecto declara "principios de privacidad por diseño" (428).

## 4. Citas y referencias
- Total de citas en texto: 0 — Total de entradas en bibliografía: 0. El único "Laudon & Laudon, 2020" (1608) es un ejemplo de la plantilla y no cuenta.
- ¿APA v7?: NO — la bibliografía solo contiene la consigna: "Es obligatorio utilizar la herramienta" (1618). No hay referencias en formato APA en ninguna parte del documento.

| Problema | Detalle (con evidencia) | Gravedad |
|---|---|---|
| Cita sin referencia | No aplica: no hay citas en texto | — |
| Referencia sin cita | No aplica: no hay entradas en bibliografía | — |
| Tecnologías sin ninguna fuente | Sección 4 completa (≈20 herramientas: YOLOv8, Gemma, Roboflow, Gemini, Groq, Claude, Supabase, MediaMTX, Tailscale, AnyDesk, TeamViewer, Plotly, SciPy, Flask, FastAPI, React, Vue, Angular, Expo Go, VS Code) sin cita en ninguna línea | Alta |
| Dato sin fuente (1) | Diagnóstico, Estado del arte: "menos del 10% de las franquicias logra un control operativo" (380) | Alta |
| Dato sin fuente (2) | MT 1.6: "Diversos estudios relacionados con el sector retail destacan la creciente adopción" (573); "Grandes cadenas comerciales utilizan actualmente sistemas" (575) | Alta |
| Dato sin fuente (3) | MT 4.6: "La plataforma opera bajo un modelo de costos de $0 USD" (1007); "una inversión operativa aproximada de $15 USD mensuales" (1014). Son los costos que sostienen RNF-02 | Alta |
| Dato sin fuente (4) | MT 4.3.4: "teniendo 20 como límite" (885), cuota diaria de Gemini sin fecha ni fuente | Media |
| Dato sin fuente (5) | MT 4.3.6: "Demuestra una baja tasa de alucinación" (905), afirmación de desempeño sin fuente | Media |
| Sección 3 sin fuentes | 3.1 a 3.6 sin ninguna cita. Ejemplo: "Sin embargo, una gran parte de estas soluciones se encuentra orientada a grandes cadenas" (753). Las opciones de mercado son categorías genéricas, no productos concretos | Alta |
| Dato sin fuente (contexto) | MT 1.1: "Dentro de Argentina, YPF constituye una de las principales empresas" (506); MT 1.4: "La mayoría de los establecimientos comerciales modernos dispone de sistemas" (543) | Media |
| Fuentes débiles | Precios y cuotas de Supabase, DigitalOcean y Firebase (4.6) y planes de AnyDesk/TeamViewer (4.7.3) tomados de sitios comerciales. Ej.: "La plataforma dispone de un plan gratuito para uso personal" (1034); "admiten una sola sesión simultánea" (1041) | Media |
| Figuras de terceros | Figuras 1 a 4: "Fuente: Hik-Connect" sin referencia completa. Si las capturas son propias, corresponde "elaboración propia" | Alta |
| URLs con tracking | No encontrado (sin utm_, fbclid ni ?si=) | — |
| Links pelados | No encontrado en el cuerpo. Único enlace en texto: "[Hikvision](https://www.hikvision.com/...)" (314, Glosario), sin formato APA | Baja |

## 5. Contaminación del Marco Teórico
**Resultado:** PARCIAL

- 3.6 Comparación entre las soluciones existentes y la propuesta del proyecto — "busca posicionarse como una alternativa que combine las ventajas" y "el sistema pretende reutilizar las cámaras IP existentes" (785). Nombra OptiFull y describe el diseño del sistema propio. Una comparación debería ser neutral y con fuente. Gravedad: Alta.
- 3.6 (cierre) — "el proyecto apunta a cubrir un espacio poco explorado" (787). Afirma el valor de la solución propia. Gravedad: Media.
- 3.5 Oportunidad de innovación — "la propuesta consiste en utilizar las mismas imágenes para asistir al personal" (775). Describe la solución propia. Gravedad: Media.
- 4.3.6 Claude API — "El modelo conceptual de implementación se basa en el consumo de su API paga" (900) y "el pipeline de visión por computadora envía resúmenes estructurados" (900). Describe la arquitectura de integración del sistema propio, no una opción de mercado. Gravedad: Alta.
- 4.3.6 (inicio) — "recibir secuencias de metadatos o fotogramas clave enviados desde el sistema de seguimiento local" (898). Describe el flujo del pipeline propio. Gravedad: Media.
- 2.4 Justificación del análisis de campo — "La propuesta tecnológica plantea reutilizar la infraestructura de videovigilancia existente" (627). Es una premisa de la solución dentro de la justificación. Gravedad: Media.
- Observar: 4.4.1 — "se analizaron los Modelos de Lenguaje Grandes (LLMs) comerciales" (919). Describe el uso de LLM en el proceso de desarrollo, no una decisión técnica. Conviene aclararlo como contexto de proceso.
- Observar: 4.7 — "Los flujos RTSP del grabador solo son accesibles desde la red local de la tienda" (1020). Es un dato del caso y puede mantenerse como contexto.
- Sin contaminación detectada: 1.1 a 1.7; 2.1 a 2.3; 2.5 a 2.11 (salvo lo indicado); 3.1 a 3.4; 4.1 a 4.3.5; 4.5; 4.6; 4.8. Estas secciones investigan o comparan sin elegir.

## 6. Acciones prioritarias
- **Crítico:** Crear la bibliografía en APA v7 y citar en el texto cada fuente de la sección 4, la sección 3 y los datos de 1.x. Incluir las referencias de las Figuras 1 a 4 (sustituir "Fuente: Hik-Connect").
- **Crítico:** Quitar la solución propia del MT: reescribir 3.5, 3.6 y 4.3.6 (líneas 775, 785-787, 898-900) como comparación neutral con fuentes. Mover la descripción de integración a la Propuesta de solución.
- **Crítico:** Sustentar con fuente o eliminar los datos de la tabla "Datos sin fuente", en especial los costos de 4.6 (líneas 1007 y 1014), "menos del 10%" (380) y "20 como límite" (885).
- **Crítico:** Eliminar los bloques de instrucciones de plantilla (líneas indicadas en la sección 3) y el texto dirigido al asistente (línea 703).
- **Importante:** Reescribir los objetivos específicos con un criterio medible (precisión, FPS, cobertura, tiempo de respuesta) en lugar de verbos de acción sin métrica (452-460).
- **Importante:** Completar la tabla de trazabilidad (sugerida) o retirar la consigna de la línea 466.
- **Importante:** Corregir las figuras: mención previa en el texto antes de la Figura 1, fuente en la forma exigida y revisar la privacidad de las personas que aparecen.
- **Importante:** Ampliar la sección 3 con opciones de mercado concretas (productos o plataformas, con pros y contras y fuente).
- **Importante:** Ajustar el glosario: quitar términos genéricos (API, Flask, React, Supabase, LLM, DOM Virtual), agregar "mermas" y "descuadre", corregir "Enrique" (316) y reordenar alfabéticamente.
- **Importante:** Unificar la denominación del trabajo ("Trabajo Final de Carrera" en 601 y 665 frente a "Informe Final de Grado") y completar la fecha de la portada.
- **Importante:** Agregar en 2.5 fecha, cantidad de entrevistados y guía de preguntas. Aclarar si el entrevistado es la gerencia o la encargada (675 y 677).
- **Menor:** Corregir "a ojo" (386) y "aliado directo" (382), la preposición faltante de la Figura 4 (408), el "Características:" pegado (216), la explicación de "RTSP" en el abstract (230) y el encabezado vacío "###" (1016).
- **Menor:** Unificar la jerarquía de encabezados del MT (H1, H3 y negrita mezclados) y actualizar el índice con las subsecciones 4.3.4 a 4.8.
- **Menor:** Verificar la grafía del apellido "Blasón" y el render de las imágenes exportadas.

Fuera de alcance (no evaluado, solo se señala): en la Pruebas de la Propuesta aparece texto de conversación, "que te pasé antes" (1540) y "sección 22" (1542).

Informe guardado en /Users/ignaciocarre/Developer/ucc/IPIs-medio-termino/correcciones/PI - 26 - OptiFULL - Blason Agostina, Nahmias Arnon, Ortiz Paulina_correccion_mt.md
