# 2 · Fundamentos del testing

## Error, defecto y falla en el módulo web

Un ejemplo del propio TP, DEF-024:

- **Error** (de una persona): al servir los archivos del panel se verificaba si el archivo existía *antes* de
  comprobar que estuviera dentro de `frontend/dist/`.
- **Defecto** (en el código): `static_files()` respondía 404 si la ruta salía de `dist/` hacia un archivo que
  existe, y 200 si el archivo no existía.
- **Falla** (lo que se observa): sin iniciar sesión, desde internet, cualquiera podía averiguar si el servidor
  tiene un `.env` o qué módulos tiene la API, comparando las respuestas.

## Modelo de desarrollo y momento de las pruebas

El módulo se desarrolla de forma **iterativa e incremental, con integración continua** (la clase del 24/08 distingue
cascada, iterativo y ágil). Cada cambio llega a `main` por un PR y el pipeline lo prueba en minutos: las pruebas
corren **durante** el desarrollo y no al final, y la regresión se ejecuta en cada push. Es el principio común a todos
los modelos: cada actividad se prueba y las pruebas empiezan desde el inicio. Los defectos de este TP lo muestran:
los que se encontraron al escribir los tests (DEF-002 a DEF-008) costaron un arreglo de pocas líneas, y los que
llegaron al análisis de SonarQube Cloud (DEF-023 a DEF-027) ya requerían revisar rutas enteras. Cuanto antes se
encuentra un defecto, más plana está la curva de costo del cambio.

**Tipos de prueba usados**, con los nombres de la clase: *regresión* (un test por defecto), *smoke* (verificación
rápida tras cada despliegue) y *sanity*: tras cada corrección se corre primero el test del defecto arreglado, y recién
después la suite completa. El resto de los tipos está en el mapa de niveles de
[03-modelos-calidad-y-niveles.md](03-modelos-calidad-y-niveles.md).

## Pruebas unitarias en Arrange – Act – Assert

Todas las pruebas del módulo siguen el patrón AAA: preparar el escenario, ejecutar una acción y comparar con lo
esperado. Sin aserción no hay prueba.

**API (pytest)**: `test/unitarios/test_seguridad.py`, regresión de DEF-027.

```python
def test_def027_video_no_sale_a_una_carpeta_vecina_con_el_mismo_prefijo(cliente, tmp_path, monkeypatch):
    # Arrange: una carpeta de videos y, al lado, otra con el mismo prefijo y un video privado
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos_privado").mkdir()
    (tmp_path / "videos_privado" / "camara_banio.mp4").write_bytes(b"privado")
    monkeypatch.setattr(video, "VIDEOS_DIR", str(tmp_path / "videos"))
    # Act: pedir el video privado saliendo de la carpeta con '..'
    r = cliente.get("/api/video/../videos_privado/camara_banio.mp4")
    # Assert: se rechaza y el contenido no viaja
    assert r.status_code in (403, 404)
    assert b"privado" not in r.data
```

**Panel (Vitest)**: `frontend/src/efectos/seguir.test.js`, regresión de DEF-020.

```js
test('DEF-020: sin Web Animations no hace nada y no tira error', () => {
  // Arrange: un navegador sin Web Animations (el botón no tiene .animate)
  conMovimiento(false)
  const boton = document.createElement('button')
  expect(boton.animate).toBeUndefined()
  // Act + Assert: el estirón del botón no corta el envío del formulario
  expect(() => estira(boton)).not.toThrow()
  expect(() => estira(boton, false, 0.5)).not.toThrow()
})
```

(Los comentarios Arrange / Act / Assert se agregan acá para leerlo; en el repositorio el patrón se respeta con
bloques separados.)

## Criterio de aceptación fijado antes de ejecutar

El resultado esperado se escribe antes de correr la prueba, no se ajusta a lo que salga:

| Prueba | Criterio, y cuándo se fijó | Qué pasó al ejecutarla |
|---|---|---|
| Stress de 40 usuarios en QA | p95 ≤ 5 s, p99 ≤ 10 s, errores ≤ 5 %, en `verificar_umbrales.py` (commit ce221c2, antes de la primera corrida en QA) | La primera corrida dio p95 de 7,6 s y el job quedó en rojo. **No se aflojó el umbral**: se buscó la causa y se mejoró el sistema (pool de conexiones), y ahí pasó con 2,4 s |
| Quality gate | Bugs críticos = 0, duplicación ≤ 5 %, cobertura sobre código nuevo ≥ 80 % (ef77d4e, antes de escribir los tests) | En rojo dos veces (b877bde, 67935ce) hasta que la cobertura llegó al umbral |
| Cada defecto | El test de regresión se escribe con el resultado correcto (por ejemplo, "responde 404") y se ejecuta **antes** del arreglo: tiene que fallar | Ver la tabla de abajo |

## Defectos reales con contraste rojo/verde

| Defecto | Rojo (el test que falla) | Verde (el arreglo) | En el pipeline |
|---|---|---|---|
| DEF-002: `/api/heatmap/image` entregaba cualquier archivo del proyecto, incluido el `.env` | 22f4f21 | 4883562 | [39466050826](https://github.com/pauliiortizz/OptiFull/actions/runs/39466050826) en rojo → [39466216477](https://github.com/pauliiortizz/OptiFull/actions/runs/39466216477) en verde |
| DEF-020 a DEF-022: el rediseño visual de `main` rompía el login sin Web Animations, inventaba un 0 % y mostraba "Failed to fetch" | 671ef55 | 54a4e45 | Subidos juntos; el rojo se verificó localmente (6 tests en rojo, todos de esos tres defectos) |
| DEF-023 a DEF-027: vulnerabilidades de la API (SSRF, oráculo de archivos, fuente de la caja sin validar, clickjacking, carpetas vecinas) | dd6a07d | ffa1629 | Subidos juntos; el rojo se verificó localmente (todos los casos de `test_seguridad.py` en rojo) |

El registro completo, con pasos, esperado y obtenido, está en [defectos.md](defectos.md) y en Jira.

## Los siete principios aplicados al módulo web

| Principio | Cómo se vio en el TP |
|---|---|
| **1. Las pruebas muestran la presencia de defectos, no su ausencia** | Con la API al 98 % de cobertura, la revisión de SonarQube Cloud encontró 5 vulnerabilidades reales, y leyendo el código apareció una sexta (DEF-027). Que todo pase no prueba que no haya defectos. |
| **2. Las pruebas exhaustivas son imposibles** | La cabecera `Range` de un video, los parámetros `t` y `dur` de un clip o las URLs de cámara admiten infinitas entradas. Se eligieron clases de equivalencia y valores límite ([05-pruebas-dinamicas.md](05-pruebas-dinamicas.md)), y el esfuerzo se puso donde el riesgo es mayor (seguridad, R2). |
| **3. Las pruebas tempranas ahorran tiempo y dinero** | Cada push a la rama de trabajo corre 808 pruebas del módulo en 1,6 minutos. DEF-020 a DEF-022 aparecieron al traer `main` a la rama, antes de llegar a `main` y a producción. |
| **4. Los defectos se agrupan** | De los 20 defectos del módulo, 10 están en cuatro archivos de la API que reciben rutas, URLs o cabeceras del usuario: `video.py` (DEF-005, 006, 007, 027), `heatmap.py` (DEF-002, 003), `productos.py` (DEF-023, 025) y `__init__.py` (DEF-024, 026). Ahí se concentró después la revisión de seguridad. |
| **5. Paradoja del pesticida** | Los tests unitarios ya no encontraban nada nuevo y el pipeline estaba en verde. Hicieron falta pruebas distintas: la de carga encontró que la API abría una conexión por pedido, el E2E con la cuenta de empleado encontró un supuesto equivocado en el propio test, y el análisis estático encontró las vulnerabilidades. |
| **6. Las pruebas dependen del contexto** | Es el panel de una tienda, en un plan gratuito, con un equipo chico conectado: la carga esperada es de 15 usuarios, no de miles, y lo crítico es la seguridad (el panel está en internet con datos de personas) y la fiabilidad, no la disponibilidad al 99,99 %. |
| **7. La falacia de la ausencia de errores** | El pipeline en verde no garantiza que el sistema sirva. Con todas las pruebas pasando, el stress daba un p95 de 7,6 s; y hoy, con todo en verde, un pedido de demo puede perderse si Resend está caído (riesgo R9). |
