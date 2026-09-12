# Skill: Modern Data-Dense UI & Product Design System

Actuá como un Lead UI/UX Designer y Frontend Engineer especializado en herramientas analíticas SaaS B2B de alto rendimiento.

## 1. Dirección de Arte & Estética Minimalista con Color
- **Base limpia:** Fondo neutro frío de bajo contraste (`#f8fafc` o `#090a0f` según modo). Evitá gradientes oscuros saturados de azul.
- **Color con propósito semántico:**
  - El color NO se usa para decorar; se reserva exclusivamente para los datos espaciales y analíticos.
  - Acento primario de interfaz: Usá un tono contemporáneo sobrio (ej. Indigo técnico `#6366f1` o Esmeralda analítico `#10b981`).
  - Capas térmicas y métricas: Paleta continua calibrada (de azul frío desaturado pasando por ámbar hasta coral cálido para calor alto), nunca colores primarios al 100% de saturación.
- **Profundidad sin sombras pesadas:** Los contenedores se delimitan con bordes ultrafinos de 1px (`border-slate-200/80` o `border-zinc-800`). Prohibido el uso de `box-shadow` difusas y tarjetas flotantes desconectadas.

## 2. Tipografía Distintiva y Técnica
- **Jerarquía:**
  - Headings y UI general: Fuente geométrica moderna como **Plus Jakarta Sans**, **Geist** o **Inter**.
  - Datos numéricos, timestamps y métricas espaciales: Fuente monoespaciada con soporte tabular estricto (**JetBrains Mono** o **Geist Mono** con clases `tabular-nums tracking-tight`).
  - Metadatos: 10px a 11px, `uppercase`, `tracking-wider`, peso mediano en gris atenuado.

## 3. Arquitectura del Layout (Spatial Analytics Hub)
- **Eliminar el "bloque vacío":** Nunca renderizar un canvas de mapa de calor sobre un fondo plano sin contexto. El canvas debe incluir un plano esquemático vectorizado (SVG/Canvas) de la tienda con zonas de interés (ROI) delimitadas.
- **Densidad de información:** Reducir paddings generales a escalas compactas (`p-3` o `p-4`). Integrar controles flotantes semitransparentes sobre el visor de mapas (toggles de calor/vectores y slider de opacidad estilo HUD técnico).
- **KPIs unificados:** Agrupar las métricas clave en una barra continua o tira superior compacta, acompañadas de micro-sparklines con gradiente tenue de relleno en lugar de líneas gruesas.