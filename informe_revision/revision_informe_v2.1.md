# Revisión del Informe de Proyecto Integrador — OptiFull v2.1

Archivo revisado: `Informe de Proyecto Integrador - Optifull - v2.1 - 2026.docx (1).pdf` (120 páginas).
Alcance: todo el documento **excepto** las secciones que todavía faltan escribir (Pruebas, Beneficios, Impacto económico, social y medioambiental, Conclusión). También se cruzó lo que dice el informe con el código del repositorio (rama `Pau`).

Prioridades:
- 🔴 **Urgente**: texto que no puede quedar en la entrega (notas internas, marcadores sin completar, contradicciones con el código).
- 🟠 **Importante**: faltan contenidos o hay incoherencias que un evaluador va a marcar.
- 🟡 **Mejora**: redacción, formato, consistencia.

---

## 1. Lo más urgente: texto que hay que borrar o completar

| # | Dónde | Qué hay | Qué hacer |
|---|---|---|---|
| 1 | Final de Anexos (pág. ~119-120) | Bloque entero **"Notas para vos (no van en el informe)"** y **"Antes de pegarlo"**, con texto pegado de un chat ("Esta sesión no se está ejecutando, por lo que no se pueden abrir sus archivos…") | Borrar completo. Antes, aplicar lo que dicen esas notas (ver puntos 6, 7 y 25). |
| 2 | Sección 2.11, después del punto 2 | *"Al final de la sección 2.11, después del punto Extracción de Footage… Va con el mismo formato que los dos puntos anteriores (título del punto en negrita, seguido de dos puntos)."* | Borrar (es una instrucción, no contenido). |
| 3 | Pruebas | *"Las pruebas ejecutadas se detallan en la Tabla n.Después va la tabla que te pasé antes, con su pie… y el párrafo del monitoreo térmico. Eso no cambia."* | Borrar la instrucción y numerar la tabla. (Se rehace cuando escribamos Pruebas). |
| 4 | Bibliografía | *"Cuando armemos la bibliografía conviene citar la documentación oficial de Ultralytics, ByteTrack, Supabase y Tailscale."* | Borrar y reemplazar por las referencias reales (ver sección 5 de esta revisión). |
| 5 | Arquitectura (capa 1) y Módulo 2 | **`[aplicación macOS]`** aparece dos veces | Completar con el nombre del programa que corre en la Mac de caja (o reescribir: "un equipo Mac que recibe el flujo y ejecuta el pipeline de caja"). |
| 6 | Pantallas | **"Figura n"** (flujo de navegación) | Numerar. Ojo: hoy la Figura 7 tiene el pie "Flujo de navegación…" pero el texto dice que muestra "la estructura general del panel". Decidir qué imagen es cuál y renumerar desde la Figura 5. |
| 7 | Pantallas → Página de bienvenida | Se menciona "Figura 5" pero **no hay pie de Figura 5** | Agregar pie: "Figura 5: Página de bienvenida de OptiFull. Fuente: elaboración propia." |
| 8 | Portada | `<dia> de Febrero de 2027` | Completar la fecha de entrega. Además, el título "EJEMPLO DE PORTADA" no debe quedar. |
| 9 | Glosario → Inferencia | *"…detectar una persona en un fotograma de video **Enrique**"* | Borrar "Enrique". |
| 10 | Tabla de pruebas de infraestructura | Celdas `[completar]` | Completar cuando escribamos Pruebas. |
| 11 | Plan de pruebas | "RF-08 clasificación de comportamiento" y "sección 22" | Con la numeración nueva es **RF-17**; "sección 22" es la página de la Tabla de Trazabilidad, no una sección. |

### Texto de la plantilla de la cátedra

Siguen pegadas las consignas de la plantilla en casi todas las secciones: "DEFINICIONES GENERALES PARA CONFECCIÓN…", "Definición / ¿Qué se espera encontrar en un Abstract?", "En esta sección se introduce…", "Por ejemplo…", "Aspectos clave a incluir en el MT", "Aspectos clave a incluir en la Propuesta de solución", "Se espera encontrar referencias a…", etc.
➡️ Confirmar con los directores si hay que quitarlas en la entrega final (lo habitual es que sí). Si se quitan, hay que **regenerar el índice**.

### Índice desactualizado

El índice llega solo hasta 4.4.1 y los números de página no coinciden. Por ejemplo: Glosario dice pág. 10 y está en la 13; Propuesta dice 54 y está en la 60; Anexos dice 63 y está en la 116. Faltan 4.3.4 a 4.3.6, 4.5, 4.6, 4.7, 4.8, y todos los subtítulos de la Propuesta (Pantallas, Diagramas, Arquitectura, Patrones, Módulos 1 a 11).
➡️ En Google Docs: usar estilos de Título 1/2/3 en todos los encabezados y actualizar la tabla de contenidos. Falta también un **índice de figuras y de tablas**.

---

## 2. Incoherencias entre el informe y el proyecto real (código)

| # | Dónde | Problema | Propuesta |
|---|---|---|---|
| 12 | Glosario: "ByteTrack / BoT-SORT" | El sistema usa **solo ByteTrack** (`bytetrack_custom.yaml`). | Dejar solo ByteTrack. Si se quiere, mencionar BoT-SORT en el Marco Teórico como alternativa evaluada. |
| 13 | 4.8.2 Frontend | Dice "React.js, complementado con **Next.js**". El proyecto usa **React 19 + Vite**, no Next.js. | Reemplazar Next.js por Vite (y agregar Vite al análisis). |
| 14 | 4.2.1 Expo Go + glosario | No existe app móvil en el proyecto (no hay React Native ni Expo). | Eliminar 4.2.1 y el término del glosario, **o** dejarlo explicando por qué se descartó la app móvil (la interfaz es web responsive). |
| 15 | 4.3.2 Gemma + glosario (LoRA, Fine-tuning) | Gemma no se usa en ninguna parte del sistema. | Eliminar, **o** mantenerlo como alternativa descartada con el motivo (por ejemplo: sin GPU no era viable correrlo localmente). Si se elimina Gemma, LoRA queda sin uso en el informe → eliminarlo del glosario. |
| 16 | 4.3.5 Groq | Dice que la LPU "presenta limitaciones significativas" para visión y que hay pocos modelos de visión. Pero **el sistema usa Groq para reidentificación** con un modelo de visión (`qwen/qwen3.6-27b`; antes `llama-4-scout`). | Reescribir: Groq ofrece modelos multimodales de visión con muy baja latencia, con cuota gratuita limitada y modelos que se dan de baja (ejemplo real: llama-4-scout retirado el 17/07/2026). |
| 17 | Propuesta, párrafo de selección tecnológica | "Se adoptó YOLOv8 **en su variante Nano**". En la implementación se usa **Nano para grabaciones y Small para RTSP en vivo**. | Corregir para que coincida con el Módulo 3. |
| 18 | Propuesta, párrafo de selección | No dice qué tecnología de mapas de calor se eligió, aunque 4.5 compara cuatro. El código usa **NumPy + kernel gaussiano propio** (`HeatmapBuilder`) e imagen con OpenCV/Matplotlib. | Agregar una frase de cierre: "De las alternativas de la sección 4.5 se adoptó…". |
| 19 | Resumen / Abstract | "Los resultados obtenidos **demuestran** la viabilidad…": todavía no hay pruebas escritas. Además dice "modelos de detección… de **productos**", cuando los productos se reconocen con un modelo multimodal (Claude Haiku 4.5) sin entrenamiento. No menciona el reconocimiento en caja. | Reescribir el resumen **al final**, después de Pruebas y Conclusión, con resultados medidos (precisión del matching, latencia, costo). |
| 20 | Diagnóstico → Oportunidades | Describe la alerta como "desplazamiento directo desde góndolas críticas hacia la salida" y "notifica de forma **instantánea**". El sistema clasifica "tomó un producto y se fue sin acercarse a la caja", y la interfaz consulta alertas **cada 20 s**. | Alinear la descripción con RF-17 y cambiar "instantánea" por "en tiempo casi real". |
| 21 | Diagnóstico / 2.8 | Se plantean problemas que el sistema **no resuelve**: mermas no facturadas de cafetería, descuadres de caja y ocupación pasiva de mesas. | Agregar en "Fuera de alcance" las mermas de cafetería. Para combos, explicar que el reconocimiento en caja registra el producto real que se lleva el cliente (sí aporta). Para ocupación de mesas, vincularlo con la métrica de permanencia por zona. |
| 22 | Objetivo específico 2 | "Seleccionar modelos… para detección de productos". Se terminó descartando un detector de productos (Módulo 8). | Reformular: "…modelos para la detección de personas y el reconocimiento de productos". |
| 23 | Objetivos específicos | Hay funciones implementadas sin objetivo: infraestructura de acceso remoto (nodo + Tailscale), autenticación/roles, exportación de reportes, CI/CD. | Agregar uno o dos objetivos, o integrarlos en los existentes. |
| 24 | 2.10 vs. Anexo del nodo | 2.10 dice 4 cámaras en salón + 2 en cocina + 1 en proveedores. El anexo de MediaMTX configura solo `camara1` y `camara2`. | Aclarar cuántas cámaras se analizan realmente y por qué ("se configuraron N rutas, una por cámara analizada…"). |
| 25 | RF-02 / Seguridad | Los roles solo ocultan secciones en el frontend; los endpoints `/api/*` **no verifican el rol** (confirmado en el código). | Dos opciones: (a) corregirlo en el código antes de la defensa (recomendado), o (b) declararlo como limitación conocida y trabajo futuro. Es una pregunta probable en la defensa. |
| 26 | Licencia | `ultralytics/` está incluido en el repo y tiene licencia **AGPL-3.0**. | Mencionarlo en el Marco Teórico (4.3.1, desventajas) y retomarlo en Impacto Económico: un uso comercial como servicio obliga a publicar el código o a comprar la licencia Enterprise de Ultralytics. |

---

## 3. Errores puntuales de redacción y formato

**Glosario**
- No está en orden alfabético: PyTorch aparece después de Inferencia, FastAPI después de IP y OpenCV antes de MediaMTX.
- **LPU**: dice "procesamiento determinista y de **alta** latencia". Debe decir **baja** latencia.
- **"Micro Frames Web"**: no es un término reconocido (probablemente se quiso decir *micro frontends*). Eliminarlo del glosario y de 4.5.3.1 ("aplicaciones basadas en micro frames web").
- **"Dispositivos LiDAR"** → la entrada debería ser "LiDAR".
- **Hik-Connect**: "**Es** la aplicación oficial…". Las demás definiciones arrancan sin verbo; unificar el estilo.
- La plantilla pide **no** definir términos genéricos de informática. Sobran o son discutibles: API, DOM Virtual, React, Flask, FastAPI, PyTorch, OpenCV. Se pueden dejar solo si se usan mucho; DOM Virtual se puede eliminar.

**Diagnóstico**
- "Actualmente, menos del 10% de las franquicias logra un control operativo y de stock verdaderamente profesional": es un dato **sin fuente**. Citarlo (por ejemplo, con la entrevista a la encargada, como comunicación personal) o eliminarlo.
- Los dos primeros párrafos de "Oportunidades" dicen casi lo mismo ("La infraestructura de cámaras ya instalada…"). Fusionarlos.
- Pie de la Figura 4: "desde un ángulo superior **el** frente de la caja" → "…superior, orientada al frente de la caja".
- Las fuentes de las Figuras 1 a 4 dicen "Hik-Connect". En APA conviene: "Fuente: captura del sistema de videovigilancia de la tienda mediante Hik-Connect."

**Marco Teórico**
- Hay frases genéricas sin cita ("Diversos estudios relacionados con el sector retail destacan…", "Grandes cadenas comerciales utilizan…"). Cada una necesita al menos una referencia.
- 4.3.4 Gemini: "teniendo 20 como límite" → "con un límite de 20 solicitudes diarias por proyecto en el plan gratuito (Google, 2026)". Hay que citarlo con fecha, porque cambia.
- 4.3.6 Claude: afirmaciones de marketing sin fuente ("rendimiento excepcional", "baja tasa de alucinación"). Bajar el tono o citar la documentación de Anthropic.
- 4.6.2: la lista numerada sigue en "3." y "4." en vez de reiniciar en 1.
- 4.5.4: verificar en el Doc que la tabla comparativa de mapas de calor no esté desarmada; en el PDF las columnas se ven corridas. Le falta número y pie ("Tabla X: … Fuente: elaboración propia").
- 3.5 y 3.6 hablan de "la propuesta de OptiFull". La plantilla dice que en el Marco Teórico **no** se habla de la solución. Se puede mover 3.6 al inicio de la Propuesta, o reformularlo como "la oportunidad identificada".
- 4.4.1 (LLMs como asistentes): está bien declararlo. Conviene ubicarlo en una sección de metodología o declaración de uso de IA, porque no es una tecnología de la solución.

**Análisis de campo**
- 2.1 a 2.7 son mayormente teoría genérica (unas 4 páginas) **sin citas**. Recortarlo y citar (Sommerville; Hernández Sampieri).
- **Faltan datos concretos del relevamiento**: cuándo fueron las visitas, cuántas fueron, a quién se entrevistó (rol, sin nombre), cuánto duró y qué se observó. Agregar una tabla resumen, por ejemplo "Fecha | Técnica | Participante | Tema".
- Mezcla de tiempos verbales: "se planificó" / "permitirá" / "constituye". Al ser un informe final, usar pasado para lo realizado.
- Se usa "Trabajo Final de Carrera" en 2.1 y 2.7; el resto dice "Proyecto Integrador". Unificar.
- Título de 2.11: "Extracción de **Footage**" → "Extracción de grabaciones" (o definir *footage* en el glosario).

**Propuesta de solución**
- "En la Figura 5 se presenta la propuesta **organiza** en tres bloques" → "…la página, que se organiza en tres bloques".
- "En la figura 7, se **demuestra** la estructura" → "En la Figura 7 se muestra…".
- Los pies de las Figuras 8 y 9 son casi idénticos. Diferenciarlos o dejar una sola.
- Tabla 1: en APA 7 el número y el título van **arriba** de la tabla, y "Fuente" abajo. Aplicar lo mismo a la Tabla 2 y a las demás.
- Configuración: es la única pantalla sin figura.
- Arquitectura, capa 1: hay viñetas mezcladas ("Ambos servicios se configuraron…" quedó como viñeta del mismo nivel que "Cámara de caja").
- La Tabla 2 se ve desarmada en el PDF ("Productor-consumid / or", "compartida" en otra fila). Revisarla en el Doc.

**Generales**
- Unificar nombres: "OptiFull" / "Optifull", "FULL" / "Full", "tienda FULL".
- La plantilla exige **texto alternativo en cada imagen**. Revisarlo en Google Docs (no se puede verificar desde el PDF).
- Hay muchas palabras sueltas una por renglón en el PDF (por ejemplo "rotación, / picos / estacionales"). Son líneas justificadas con saltos de línea manuales dentro del párrafo. Buscarlas y quitarlas.

---

## 4. Lo que falta en las secciones ya escritas

1. **Tabla de trazabilidad** (está vacía). Se puede armar ya: Objetivo específico → RF que lo cubren → módulo → evidencia (prueba o figura). Después, en Pruebas, se completa la columna de evidencia. Esbozo:

   | Objetivo específico | RF | Módulo | Evidencia |
   |---|---|---|---|
   | Investigar el dominio mediante trabajo de campo | — | — | Secciones 2.8 a 2.11, Anexo de entrevista |
   | Captura de video por RTSP | RF-04, RF-05 | Mód. 2 | Tabla de pruebas de infraestructura |
   | Detección y seguimiento de personas | RF-06 a RF-10 | Mód. 3 | `test_tracking_eventos.py` + validación sobre video |
   | Mapas de calor, flujo y espera en caja | RF-11 a RF-14, RF-27 | Mód. 6, 9 | Figuras del Dashboard + `test_calcular_stats.py` |
   | Reconocimiento de productos | RF-21 a RF-25 | Mód. 8 | `test_matching.py`, `test_motion.py` |
   | Comportamiento sospechoso | RF-15 a RF-20 | Mód. 4, 5 | `test_eventos.py` + video con hurto simulado |
   | Interfaz web | RF-26, RF-28, RNF-09 | Mód. 10 | Figuras 5 a 12 |

2. **Marco teórico de lo que efectivamente se usa.** Hoy la Propuesta usa tecnologías que el Marco Teórico nunca presentó:
   - **Seguimiento multiobjeto**: ByteTrack (y BoT-SORT o DeepSORT como alternativas).
   - **Reidentificación de personas (ReID)** y descriptores de apariencia: histogramas HSV y distancia de Bhattacharyya.
   - **Alternativas de detectores**: YOLOv8 frente a YOLO11, RT-DETR o Faster R-CNN, para justificar la elección. El dataset **COCO**.
   - **Reconocimiento de productos zero-shot con modelos multimodales** frente a un detector entrenado por SKU. Hoy esto solo se justifica en el Módulo 8.
   - **Coincidencia difusa de texto**: distancia de Levenshtein, librería RapidFuzz.
   - **Flask** como opción propia, no solo como contraparte de FastAPI. **Vite.**
   - **Despliegue**: Docker, Render y GitHub Actions (CI/CD).
   - **Cámara IP con smartphone** (IP Camera Lite, MJPEG) y **FFmpeg**.
   - Generación de reportes: Matplotlib, fpdf2, openpyxl (puede ser una línea).

3. **Marco legal y ético (falta por completo y es importante).** El sistema filma y analiza personas. Hay que citar la **Ley 25.326 de Protección de Datos Personales** y la **Disposición 10/2015 de la Dirección Nacional de Protección de Datos Personales** sobre videovigilancia, más el concepto de **privacidad por diseño** (Cavoukian). También conviene mencionar cartelería, consentimiento del establecimiento para usar las grabaciones y resguardo de la evidencia. Esto además alimenta el futuro Impacto Social.

4. **Opciones similares en el mercado (sección 3).** No nombra **ningún producto real**. Agregar ejemplos concretos con cita y una **tabla comparativa**. Candidatos:
   - Videovigilancia con IA: Hikvision (AcuSense / DeepinView), Axis (Object Analytics / People Counter).
   - Analítica retail: RetailNext, Sensormatic ShopperTrak, V-Count.
   - Detección de hurto con cámaras existentes: **Veesion** y Everseen (son los competidores más directos).
   - Control de góndola: Trax.

   Criterios para la tabla: reutiliza cámaras existentes, métricas de flujo, detección de hurto, reconocimiento de productos, costo/escala, privacidad.

5. **Metodología de trabajo.** No aparece cómo se organizó el equipo: metodología (por ejemplo Scrum o Kanban), ramas por integrante en GitHub, cronograma. Puede ir como subsección breve o en Anexos.

6. **Declaración de uso de IA generativa** en el desarrollo y la redacción. Ya se nombran GPT y Claude en 4.4.1; conviene una declaración explícita, si la universidad o la cátedra lo pide.

7. **Limitaciones conocidas**: roles sin control en la API, dependencia de cuotas de proveedores de IA, cámaras a baja resolución (substream 640×360), CPU sin GPU. Se pueden ubicar al final de la Propuesta o en la Conclusión.

---

## 5. Bibliografía sugerida (APA 7)

⚠️ Hoy el informe **no tiene ninguna cita**. La plantilla exige usar *Herramientas → Citas* de Google Docs. Las referencias de software y sitios web llevan **fecha de consulta** cuando el contenido cambia.

**Visión por computadora e IA (libros y papers)**
- Goodfellow, I., Bengio, Y., & Courville, A. (2016). *Deep learning*. MIT Press. → Glosario (Deep Learning), Marco Teórico.
- Szeliski, R. (2022). *Computer vision: Algorithms and applications* (2.ª ed.). Springer. → Definición de visión por computadora.
- Russell, S., & Norvig, P. (2021). *Artificial intelligence: A modern approach* (4.ª ed.). Pearson. → Presentación del tema.
- Redmon, J., Divvala, S., Girshick, R., & Farhadi, A. (2016). You only look once: Unified, real-time object detection. En *Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition* (pp. 779–788). → 4.3.1.
- Jocher, G., Chaurasia, A., & Qiu, J. (2023). *Ultralytics YOLOv8* (Versión 8.0.0) [Software]. https://github.com/ultralytics/ultralytics → 4.3.1, Módulo 3.
- Lin, T.-Y., Maire, M., Belongie, S., Hays, J., Perona, P., Ramanan, D., Dollár, P., & Zitnick, C. L. (2014). Microsoft COCO: Common objects in context. En *European Conference on Computer Vision* (pp. 740–755). Springer. → Módulos 3 y 4.
- Zhang, Y., Sun, P., Jiang, Y., Yu, D., Weng, F., Yuan, Z., Luo, P., Liu, W., & Wang, X. (2022). ByteTrack: Multi-object tracking by associating every detection box. En *European Conference on Computer Vision* (pp. 1–21). Springer. → Glosario, Módulo 3.
- Ye, M., Shen, J., Lin, G., Xiang, T., Shao, L., & Hoi, S. C. H. (2022). Deep learning for person re-identification: A survey and outlook. *IEEE Transactions on Pattern Analysis and Machine Intelligence, 44*(6), 2872–2893. → ReID.
- Swain, M. J., & Ballard, D. H. (1991). Color indexing. *International Journal of Computer Vision, 7*(1), 11–32. → Histogramas de color.
- Bhattacharyya, A. (1943). On a measure of divergence between two statistical populations defined by their probability distributions. *Bulletin of the Calcutta Mathematical Society, 35*, 99–109. → Similitud de apariencia.
- Levenshtein, V. I. (1966). Binary codes capable of correcting deletions, insertions, and reversals. *Soviet Physics Doklady, 10*(8), 707–710. → MatchingAgent.
- Hu, E. J., Shen, Y., Wallis, P., Allen-Zhu, Z., Li, Y., Wang, S., Wang, L., & Chen, W. (2021). *LoRA: Low-rank adaptation of large language models* (arXiv:2106.09685). arXiv. → Solo si queda LoRA.
- Gemma Team. (2024). *Gemma: Open models based on Gemini research and technology* (arXiv:2403.08295). arXiv. → Solo si queda Gemma.
- Shi, W., Cao, J., Zhang, Q., Li, Y., & Xu, L. (2016). Edge computing: Vision and challenges. *IEEE Internet of Things Journal, 3*(5), 637–646. → Glosario (Edge Computing).

**Librerías científicas**
- Bradski, G. (2000). The OpenCV library. *Dr. Dobb's Journal of Software Tools*.
- Harris, C. R., et al. (2020). Array programming with NumPy. *Nature, 585*, 357–362.
- Virtanen, P., et al. (2020). SciPy 1.0: Fundamental algorithms for scientific computing in Python. *Nature Methods, 17*, 261–272.
- Hunter, J. D. (2007). Matplotlib: A 2D graphics environment. *Computing in Science & Engineering, 9*(3), 90–95.
- Paszke, A., et al. (2019). PyTorch: An imperative style, high-performance deep learning library. En *Advances in Neural Information Processing Systems 32*.

**Redes y streaming**
- Schulzrinne, H., Rao, A., & Lanphier, R. (1998). *Real Time Streaming Protocol (RTSP)* (RFC 2326). IETF. → Glosario RTSP.
- Donenfeld, J. A. (2017). WireGuard: Next generation kernel network tunnel. En *Network and Distributed System Security Symposium (NDSS)*. → Glosario, 4.7.2.
- Antonakakis, M., et al. (2017). Understanding the Mirai botnet. En *26th USENIX Security Symposium* (pp. 1093–1110). → 4.7.4 ("los dispositivos de videovigilancia son objetivos frecuentes de ataques").

**Ingeniería de software (análisis de campo, requerimientos, patrones)**
- Sommerville, I. (2016). *Software engineering* (10.ª ed.). Pearson. → 2.2, requerimientos.
- Pressman, R. S., & Maxim, B. R. (2020). *Software engineering: A practitioner's approach* (9.ª ed.). McGraw-Hill.
- Hernández Sampieri, R., & Mendoza Torres, C. P. (2018). *Metodología de la investigación: Las rutas cuantitativa, cualitativa y mixta*. McGraw-Hill. → 2.3 (entrevistas, observación).
- Cohn, M. (2004). *User stories applied: For agile software development*. Addison-Wesley. → Historias de usuario.
- Gamma, E., Helm, R., Johnson, R., & Vlissides, J. (1994). *Design patterns: Elements of reusable object-oriented software*. Addison-Wesley. → Strategy, Mediator, Observer.
- Fowler, M. (2002). *Patterns of enterprise application architecture*. Addison-Wesley. → Repository.
- Hohpe, G., & Woolf, B. (2003). *Enterprise integration patterns*. Addison-Wesley. → Integración por base de datos compartida.

**Privacidad y marco legal**
- Ley 25.326 de Protección de los Datos Personales. (2000). *Boletín Oficial de la República Argentina*.
- Dirección Nacional de Protección de Datos Personales. (2015). *Disposición 10/2015* [Condiciones de licitud para la recolección de datos mediante videovigilancia].
- Cavoukian, A. (2009). *Privacy by design: The 7 foundational principles*. Information and Privacy Commissioner of Ontario.

**Retail y contexto**
- YPF. (s. f.). *Tiendas FULL* [Sitio web] y/o *Memoria y balance anual*. → Cantidad de estaciones y tiendas (1.1).
- National Retail Federation. (2023). *National Retail Security Survey*. → Pérdidas por hurto en retail (Diagnóstico, 1.6).
- Underhill, P. (2009). *Why we buy: The science of shopping*. Simon & Schuster. → Comportamiento del cliente en tienda.
- Sitios oficiales de los productos de la sección 3 (Veesion, Everseen, RetailNext, ShopperTrak, V-Count, Hikvision, Axis, Trax), con fecha de consulta.

**Documentación oficial (con fecha de consulta)**
Ultralytics Docs (YOLOv8, Tracking, Heatmaps); Anthropic (modelos Claude, Haiku 4.5, structured outputs, precios); Google AI for Developers (Gemini API, rate limits); GroqCloud Docs; Roboflow Docs; Supabase Docs (pricing, pausa de proyectos inactivos); Tailscale Docs (key expiry, DERP); MediaMTX (repositorio bluenviron/mediamtx); Hikvision (URL RTSP `/Streaming/Channels/`); Flask; React; Vite; Docker; Render; GitHub Actions; Plotly; Visual Studio Code; Expo (solo si queda).

### Dónde poner las citas

| Sección | Qué citar |
|---|---|
| Presentación del tema / 1.6 | Estudios de adopción de IA en retail (NRF, informes de consultoras) |
| Diagnóstico | El "menos del 10%", y la entrevista como comunicación personal |
| Glosario | Cada definición técnica (Ultralytics, ByteTrack, RFC RTSP, WireGuard, etc.) |
| 2.x | Sommerville / Hernández Sampieri |
| 3.x | Sitios de cada producto comparado |
| 4.x | Documentación oficial de cada tecnología |
| Propuesta / Patrones | Gamma et al., Fowler, Hohpe & Woolf |
| Privacidad (RNF-01) | Ley 25.326, Disposición 10/2015, Cavoukian |

---

## 6. Glosario: términos que faltan

Términos que se **usan en el informe y no están definidos** (en orden alfabético):

- **Afluencia / flujo de clientes**: cantidad de personas que ingresan en un período.
- **API Key / clave de API**: credencial para consumir los servicios de Claude, Gemini y Groq.
- **Bounding box (caja delimitadora)**: aparece en 4.3.1 y en el Módulo 3.
- **Centroide**: punto central de la caja delimitadora, usado para el mapa de calor.
- **CI/CD (integración y despliegue continuos)**: Módulo 11.
- **COCO (Common Objects in Context)**: dataset con el que vienen entrenados los modelos YOLOv8.
- **Combo**: término del dominio, clave en 2.8.
- **Cuota / límite de solicitudes (rate limit)**.
- **Dato biométrico / dato personal**: según la Ley 25.326; refuerza RNF-01.
- **Descriptor de apariencia no biométrico**.
- **Distancia de Bhattacharyya** o **histograma de color HSV**.
- **FPS (fotogramas por segundo)**.
- **Footage**: usado en el título de 2.11; si no, cambiar el título.
- **Franquicia**.
- **Góndola** y **heladera exhibidora**.
- **Latido (heartbeat)**: Módulo 7.
- **Merma**: término del dominio, clave en 2.8.
- **MJPEG**: formato de la cámara de caja.
- **Modelo multimodal**.
- **Nodo de captura**: concepto propio del proyecto.
- **Oclusión**: se usa muchísimo.
- **Pérdida desconocida / shrinkage**: descuadre entre stock teórico y real.
- **Permanencia (dwell time)**.
- **Privacidad por diseño (Privacy by Design)**.
- **Prompt**.
- **Reidentificación (ReID)**: concepto central del Módulo 3.
- **Reposición**.
- **SKU (Stock Keeping Unit)**: aparece en Fuera de alcance y en el Módulo 8.
- **Stock teórico / stock físico**.
- **Tasa de conversión**: RF-27.
- **Token**: unidad de facturación de los LLM, en 4.3.6.
- **Tracking / seguimiento multiobjeto**: hoy solo aparece dentro de ByteTrack.
- **Umbral de confianza**.
- **Zero-shot**: Módulo 8.
- **Zona de interés / polígono de zona**: se puede unir con ROI.

Opcionales, si se mantienen en el texto: Docker / contenedor, FFmpeg, Render (PaaS), Hikvision, Flujo principal (mainstream, como par del substream existente).

Términos para **eliminar o corregir**: BoT-SORT, Expo Go (si se quita 4.2.1), Micro Frames Web, DOM Virtual, LoRA y Fine-tuning (si se quita Gemma), y el error de LPU ("alta latencia").

---

## 7. Anexos: qué agregar o mejorar

**Existentes**
- *Pasos para acceder a las NVRs…* → corregir el título ("al NVR"), convertirlo en lista numerada y agregar capturas de cada paso con pie de figura.
- *Configuración del nodo de captura* → está muy bien. Agregar las rutas de las cámaras realmente usadas y una nota de seguridad sobre la contraseña de AnyDesk (no publicarla y rotarla).

**Para agregar**
1. **Guía de la entrevista semiestructurada** (las preguntas) y un **resumen de respuestas**, sin datos personales. Respalda todo el Análisis de campo.
2. **Registro de visitas al local** (fecha, objetivo, participantes) y **plano del local** con la ubicación y el campo de visión de cada cámara.
3. **Autorización del establecimiento** para usar las grabaciones (aunque sea una nota). Importante por el marco legal.
4. **Esquema completo de la base de datos** (`db/schema.sql` o el DER completo; en el cuerpo va el simplificado).
5. **Listado de endpoints de la API REST** (método, ruta, descripción, rol que debería poder usarlo).
6. **Prompts** usados en la reidentificación y en VisionAgent, con el esquema JSON de salida. Es clave para la reproducibilidad.
7. **Tabla de parámetros de calibración** (`deteccion/config.py` y `deteccion_productos/config.py`): umbrales de confianza, radio del mapa de calor, umbrales de matching (82/12), estabilidad (150 ms), con el motivo de cada valor.
8. **Configuración de zonas por cámara**: capturas con los polígonos dibujados.
9. **Pipeline de CI/CD** (`.github/workflows/pipeline.yml`) y `render.yaml`, o un diagrama de las etapas.
10. **Manual de usuario breve**: cómo iniciar el análisis en vivo y cómo operar la caja.
11. **Registro de costos reales de las APIs** (tokens y USD por día de prueba). Sirve directo para el Impacto Económico.
12. **Cronograma / Gantt** y distribución de tareas por integrante.
13. **Enlace al repositorio** y versión entregada (tag o commit).

---

## 8. Antes de escribir las secciones finales

Para que Pruebas, Beneficios, Impacto económico y Conclusión salgan bien, conviene juntar ahora:
- **Métricas medidas**: precisión del matching en caja sobre N productos reales, falsos positivos de hurto sobre los videos, latencia de VisionAgent, FPS del pipeline en vivo, temperatura y uptime del nodo.
- **Costos**: Surface Pro 3 (reutilizada o precio de mercado), iPhone, Render (QA + Prod), Supabase (plan gratuito o Pro), consumo de Claude/Gemini/Groq por día y horas de desarrollo. Con eso se arma el estudio de costos y el ROI frente a las pérdidas por hurto que estime la encargada.
