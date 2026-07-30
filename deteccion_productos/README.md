# Reconocimiento de producto en caja con LLM (OptiFull)

Módulo de tesis: identificación de productos en caja usando un LLM
con visión para extraer datos del envase en JSON, y matching contra
la base de productos existente para descuento automático de stock.

## Arquitectura

```
CaptureAgent -> MotionAgent -> VisionAgent(LLM) -> MatchingAgent -> StockAgent
  (video)    (¿producto     (JSON del producto)  (busca en BD    (descuenta)
             estable?)                            por campos)
```

### Por qué este diseño

- **NO se fotografía cada producto ni se entrena ningún modelo.** El
  LLM ya sabe cómo se ve una Coca-Cola.
- **NO hay que cargar aliases a mano.** La BD tiene los campos
  naturales (marca, variante, tamaño) que cualquier sistema de
  gestión ya usa.
- **El LLM se llama SOLO cuando hace falta.** El `MotionAgent`
  detecta cuando la cajera apoya un producto y no se mueve → recién
  ahí se dispara la llamada al modelo. Sin esto gastaríamos muchísimo
  llamando por cada frame.

### Nota sobre el término "agentes"

Los módulos se llaman `*Agent` por convención de nombres, pero **solo
`VisionAgent` invoca un LLM**. El resto (`MotionAgent`,
`MatchingAgent`, `StockAgent`, `CashierInterfaceAgent`) son clases
deterministas sin razonamiento propio. Es decir: esto es un pipeline
modular con una única etapa basada en IA, no un sistema multiagente
en el sentido de agentes autónomos con su propio loop de decisión.
Vale la pena ser precisos con esto en la redacción de la tesis.

### Limitación conocida: loop síncrono

`main.py` captura y analiza en el mismo hilo: mientras se espera la
respuesta del LLM, la captura de frames queda pausada. A 3-5 fps y
con confirmación manual de la cajera no debería notarse, pero es una
limitación explícita del prototipo (no un descuido) si se lo lleva a
un escenario con mayor throughput.

## Instalación

```bash
cd ypf_checkout
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Configurar API key de Anthropic

Necesitás una API key de https://console.anthropic.com

En Windows (una vez, permanente):
```
setx ANTHROPIC_API_KEY "sk-ant-tu-key-aca"
```
Cerrás y volvés a abrir la terminal para que agarre.

**Costo estimado**: ~$0.001 por producto identificado (Haiku 4.5).
Para 500 ventas/día son ~$0.50/día ≈ $15/mes.

## Puesta en marcha

### 1) Cargar productos

Editá `data/productos.csv`. Estructura:

| Columna | Ejemplo | Descripción |
|---|---|---|
| `sku` | SKU002 | Código único |
| `nombre` | Coca-Cola Zero 500ml | Nombre canónico |
| `marca` | Coca-Cola | Marca |
| `variante` | Zero | Zero / Light / Original / Manzana / etc |
| `tamano_valor` | 500 | Número |
| `tamano_unidad` | ml | ml, l, g, kg (ver nota) |
| `categoria` | gaseosa | Para filtrar/reportar |
| `cantidad` | 40 | Stock inicial |
| `precio` | 1200 | Opcional |

**Todos campos naturales** — los que ya tenés en cualquier sistema.

**Sobre `tamano_unidad`**: cargá siempre el peso o volumen neto real
impreso en el envase, incluso para productos que se venden como pieza
entera (alfajores, chocolates, snacks) — ej. un alfajor va con `46, g`,
no con `1, unidades`. La cámara lee ese peso/volumen del envase, no un
conteo, así que si el catálogo no tiene con qué compararlo el
matching no puede funcionar por más que el resto del producto
coincida. `unidades` queda solo como último recurso para el puñado de
casos donde genuinamente no hay ningún peso/volumen legible.

```bash
python setup_db.py
```

### 2) Probar el matching sin gastar API

```bash
python test_matching.py
```

Simula respuestas del LLM y valida el matching. Corrí acá y da 9/9.

### 2b) Probar la detección de estabilidad sin cámara

```bash
python test_motion.py
```

Prueba `MotionAgent` con frames sintéticos (numpy) para validar la
lógica de estabilidad/escena-nueva sin necesitar video real. Da 5/5.
Útil como referencia antes de calibrar `UMBRAL_ESTABILIDAD` y
`UMBRAL_ESCENA_NUEVA` en `config.py` con grabaciones reales.

### 3) Probar con video

```bash
python main.py --source data/videos/tu_video.mp4
```

O con ROI (más preciso, ahorra tokens):

```bash
python main.py --source data/videos/tu_video.mp4 --roi 400,200,900,700
```

### 4) Producción

```bash
python main.py --source rtsp://user:pass@ip:554/stream1
```

## Ejemplo de flujo completo

1. Cajera apoya una Coca Zero de 500ml bajo la cámara.
2. `MotionAgent` detecta 3 frames seguidos sin movimiento → dispara.
3. `VisionAgent` manda el frame a Claude Haiku 4.5, que devuelve:
   ```json
   {
     "producto_detectado": true,
     "marca": "Coca-Cola",
     "nombre_producto": "Coca-Cola Zero",
     "variante": "Zero",
     "tamano": {"valor": 500, "unidad": "ml"},
     "categoria": "gaseosa",
     "confianza": 0.95
   }
   ```
4. `MatchingAgent` puntúa marca + variante + tamaño contra CADA
   producto de la base (nadie se descarta de antemano por un solo
   campo) y se queda con el de mejor score combinado → Coca-Cola Zero
   500ml gana muy por encima del resto → reconocido.
5. `StockAgent` descuenta SKU002 y registra transacción con la
   confianza del LLM y el JSON completo (para métricas de tesis).

**Nota sobre errores de lectura del LLM**: si en el paso 3 el modelo
hubiera leído mal el envase y devuelto `"marca": "Coca Colla"` o
`"tamano": {"valor": 480, "unidad": "ml"}` (en vez de 500), el
matching igual encuentra SKU002. Tanto el texto (marca/variante) como
el tamaño se puntúan de forma proporcional al error, no con un corte
exacto: un error chico de lectura en un campo no tira abajo todo el
resultado si el resto encaja bien. Ver el docstring de
`agents/matching_agent.py` para el detalle de por qué ningún campo
descarta un candidato por sí solo.

## Métricas útiles para tesis

Como cada transacción guarda `confianza_llm`, `estado_matching` y
el JSON crudo del modelo, podés extraer:

```sql
-- % de descuentos automáticos (sin intervención)
SELECT
  SUM(CASE WHEN confirmado_por_cajera = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*)
    AS pct_automaticos
FROM transacciones;

-- Confianza promedio del LLM
SELECT AVG(confianza_llm) FROM transacciones;

-- Productos con más problemas (baja confianza recurrente)
SELECT sku, AVG(confianza_llm), COUNT(*) FROM transacciones
GROUP BY sku ORDER BY AVG(confianza_llm) ASC LIMIT 10;
```

## Próximos pasos

1. Correr `test_matching.py` para validar la base.
2. Grabar 2-3 videos cortos mostrando productos frente a la cámara
   (o extraer fragmentos de las grabaciones YPF donde se vean).
3. Ajustar `roi` según la posición de la cámara real.
4. Calibrar los umbrales de `config.py` (`UMBRAL_CONFIANZA_LLM`,
   `FRAMES_PARA_ESTABLE`, etc.) con pruebas reales.
5. Implementar UI de confirmación para la cajera (Tkinter o webapp
   con Flask + WebSocket).
6. (Opcional) Caché por hash de imagen para no volver a llamar al
   LLM si el frame es casi igual a uno reciente.
