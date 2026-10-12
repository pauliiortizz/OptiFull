# Anexo — Registro de la entrevista inicial

## 1. Datos generales

| Aspecto | Detalle |
|---|---|
| Fecha | 24 de abril de 2026 |
| Lugar | Tienda FULL de una estación de servicio YPF, localidad de Piquillín, provincia de Córdoba |
| Técnica | Entrevista semiestructurada presencial, complementada con un recorrido de observación por el salón, la caja, la cocina, el depósito y el patio de descarga |
| Entrevistadores | Los tres integrantes del equipo de proyecto |
| Entrevistados | Gerente de la tienda y propietarios de la estación de servicio |
| Registro | Notas de campo y transcripción de la conversación, consolidadas en un documento de trabajo del equipo |

*Por razones de confidencialidad, se omiten los nombres de las personas entrevistadas y de terceros mencionados durante la entrevista.*

## 2. Guía de preguntas

La guía se organizó en bloques temáticos. Se utilizó como orientación y no como un cuestionario cerrado, lo que permitió profundizar en los temas que surgieron durante la conversación.

1. **Objetivo del proyecto y necesidades.** ¿Qué problemas operativos encuentran actualmente en la tienda? ¿Cómo detectan hoy un problema y cuánto tardan en hacerlo? ¿Con qué frecuencia ocurren incidentes? ¿Hay métricas que quieran medir? Si contaran con datos automáticos sobre circulación, stock y comportamiento de clientes, ¿qué decisiones les ayudarían a tomar?
2. **Infraestructura de cámaras.** ¿Cuántas cámaras hay en la estación y cuántas dentro de la tienda? ¿Qué resolución tienen? ¿Cuentan con visión nocturna y audio? ¿Permiten acceder al video mediante RTSP? ¿Qué sistema de grabación (DVR/NVR) y qué programa utilizan? ¿Quién administra el sistema?
3. **Ubicación y cobertura.** ¿Dónde están ubicadas las cámaras y qué sector cubre cada una? ¿Hay zonas sin cobertura que deberían cubrirse?
4. **Red y conectividad.** ¿Las cámaras se conectan por cable o por Wi-Fi? ¿La conexión a internet es estable?
5. **Almacenamiento.** ¿Dónde y por cuánto tiempo se conservan las grabaciones? ¿Es posible obtener grabaciones históricas para el desarrollo?
6. **Espacio físico.** ¿Existe un plano del local? ¿Qué sectores son los más importantes para las ventas? ¿La disposición de las góndolas cambia con frecuencia?
7. **Control de stock.** ¿Cómo se realiza actualmente el control y la reposición? ¿Dónde se almacena la mercadería? ¿Qué problemas existen con el inventario? ¿Qué productos tienen mayor rotación?
8. **Operación diaria.** ¿Cuántas personas trabajan en la tienda y cuántas cajas hay? ¿Cómo se decide abrir una caja adicional?
9. **Playa de carga (exploratorio).** ¿Hay cámaras orientadas a la playa? ¿Sería útil identificar automáticamente vehículos?
10. **Escalabilidad e integración.** ¿Estarían dispuestos a agregar cámaras o a integrar el sistema con otros sistemas?

Además, se definió una lista de aspectos a observar durante el recorrido: iluminación, zonas oscuras, reflejos en vidrios y heladeras, objetos que obstruyen la visión, altura y ángulo de las cámaras, ubicación de góndolas y cajas, y zonas cubiertas por cada cámara.

## 3. Síntesis de las respuestas

### 3.1 Control de stock y circuito de la mercadería

- Las compras ingresan al depósito interno mediante factura o remito. Luego, la mercadería se traslada al salón y el traspaso se registra en el sistema con una tablet y un escáner de códigos de barras.
- La salida de mercadería se registra únicamente por factura de venta o por un remito interno, utilizado para roturas, vencimientos u obsequios. Según la entrevistada, para que el stock se mantenga correcto, toda salida debe registrarse en el sistema.
- El control se realiza por conteo manual. La reposición se basa en la observación visual de los faltantes en góndola, no en los datos del sistema.
- Los cortes de conectividad o las fallas de la tablet pueden impedir el registro de algunos traspasos.
- Se producen descuadres entre variedades de un mismo producto. Ocurre sobre todo en los **combos**: se factura una bebida y el cliente retira otra del mismo precio. También ocurre con productos de envase similar (por ejemplo, variedades de una misma gaseosa que solo difieren en el color de la etiqueta, o snacks de presentación parecida). El total de unidades coincide, pero no la cantidad por variedad.
- Los **hurtos se detectan después del hecho**, al controlar el stock. Los productos más vulnerables son los de alto valor y fácil acceso, como las papas fritas en tubo.
- En los momentos de mucha afluencia, el personal no puede supervisar al mismo tiempo la caja y las góndolas.

### 3.2 Planogramas y objetivos comerciales

- La ubicación de los productos en góndolas, heladeras y exhibidores está definida por YPF mediante planogramas, que incluyen acuerdos con las marcas (por ejemplo, una puerta completa de heladera asignada a una marca de bebidas).
- Los planogramas se actualizan cuando se dan de baja productos, manteniendo la misma marca en la misma ubicación. El franquiciado no puede reubicar productos libremente.
- Ante la falta de un producto, el espacio se completa con productos de la misma marca o con los adyacentes, para evitar el impacto visual de una góndola vacía.
- Los productos de mayor rentabilidad son los de **cafetería y cocina** (por ejemplo, hamburguesas). Además, la tienda tiene como objetivo comercial alcanzar un porcentaje de ventas de los productos de marca propia FULL dentro del rubro kiosco.

### 3.3 Afluencia de clientes y picos de demanda

- Los momentos de mayor afluencia se dan al mediodía y durante los fines de semana largos.
- La tienda recibe **colectivos con contingentes de alrededor de 40 personas**. Las temporadas más intensas son noviembre y diciembre (viajes de estudio) y marzo y abril (contingentes de jubilados). Algunos coordinadores avisan con anticipación, lo que permite prever la mercadería necesaria.
- El salón cuenta con aproximadamente **60 lugares sentados** en el interior y unos 20 en el exterior.
- El personal habitual es de dos personas (excepcionalmente tres), una de ellas en la cocina. Cuando la persona de caja también debe preparar cafetería, se forman demoras.
- La mayor impaciencia de los clientes no se produce al esperar para pagar, sino al **esperar un pedido ya abonado** (café o comida).
- Se observa que **mayor movimiento de personas no implica mayores ventas**. Por eso, la entrevistada consideró útil conocer la proporción entre ingresos de personas y compras, y el gasto promedio.

### 3.4 Uso del salón

- Hay clientes que utilizan el salón como espacio de trabajo o de espera (viajantes, transportistas, trabajadores de la zona). Permanecen varias horas con un consumo mínimo, ocupan mesas y usan la conectividad del local.
- La entrevistada consideró útil medir los **tiempos de permanencia**. También mencionó que una permanencia prolongada sin consumo puede, en algunos casos, ser una señal de alerta.

### 3.5 Uso actual de las cámaras

- No existe un centro de monitoreo ni una pantalla de visualización permanente. Las cámaras se consultan **desde una aplicación en el celular**, solo cuando ocurre un incidente.
- Los motivos de consulta más frecuentes son: objetos olvidados por clientes (carteras, billeteras, tarjetas, celulares; aproximadamente una vez al mes), errores de cobro con tarjeta que deben vincularse con un cliente y, eventualmente, caídas de personas.
- En esas revisiones, la nitidez de las imágenes resultó a veces insuficiente.
- Cámaras informadas: **cuatro en el salón y dos en la cocina**. El depósito interno no tiene cámaras; hay una en el patio de descarga de mercadería.
- La administración del sistema de cámaras está a cargo de un proveedor técnico externo. Las cámaras no registran audio.
- Según la entrevistada, la conexión a internet es actualmente más estable que en el pasado.

### 3.6 Faltantes de efectivo y consumos no facturados

- Al cierre de caja suelen existir pequeñas diferencias.
- En la cafetería pueden prepararse productos para clientes habituales que se cobran sin emitir el ticket correspondiente. Esto genera sobrantes de efectivo sin respaldo en el sistema. La entrevistada sugirió que sería útil estimar la cantidad de cafés preparados por turno.

### 3.7 Expectativas sobre la herramienta

- No se espera que el personal monitoree el sistema de forma permanente. Lo que se espera es que el sistema **emita alertas** ante situaciones relevantes y que genere un **registro o informe** (diario, semanal o por filtro). Así, ante un faltante o una diferencia de caja, se podría consultar en qué horario ocurrieron situaciones sospechosas y revisar la grabación puntual.
- Se valoró que la información se presente en forma simple: cantidades, porcentajes y gráficos.
- Se mencionó como alternativa recibir las notificaciones en el celular.

### 3.8 Ideas adicionales surgidas en la entrevista

Durante la conversación se mencionaron otras aplicaciones posibles, que quedaron fuera del alcance del proyecto: el registro de patentes en la playa de carga para identificar clientes frecuentes, el conteo de ingresos a los sanitarios para programar su limpieza, la detección del medio de pago utilizado, la detección de caídas y la de objetos olvidados.

## 4. Hallazgos y su relación con el proyecto

| Hallazgo | Tratamiento en OptiFull |
|---|---|
| Descuadre entre stock físico y stock en sistema (combos y productos similares) | Abordado parcialmente: reconocimiento del producto real en caja (Módulo 8) |
| Hurtos detectados recién al controlar el stock | Abordado: clasificación de visitas y alertas con evidencia (Módulos 4 y 5) |
| Mucho movimiento de personas sin ventas proporcionales | Abordado: flujo de personas y tasa de conversión (RF-26, RF-27) |
| Colas y demoras en momentos pico | Abordado parcialmente: congestión por día y hora, y tiempo de espera en caja (RF-27) |
| Uso prolongado del salón con bajo consumo | Abordado parcialmente: permanencia por zona (RF-27) |
| Decisiones de reposición y de personal basadas en la intuición | Abordado: Dashboard y reportes (Módulos 9 y 10) |
| Cámaras utilizadas solo de forma reactiva | Abordado: objetivo central del proyecto |
| Desconocimiento de zonas de mayor circulación | Abordado: mapas de calor (Módulo 6) |
| Consumos de cafetería no facturados | Fuera de alcance |
| Predicción de picos y comparación entre sucursales | Fuera de alcance (trabajo futuro) |
| Patentes, sanitarios, medios de pago, caídas y objetos olvidados | Fuera de alcance |

*Fuente: elaboración propia a partir de la entrevista realizada.*
