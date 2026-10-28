# Cómo ejecutar las pruebas del módulo web delante del docente

Todo se corre desde la **raíz del repositorio** (la carpeta `OptiFull`), en una terminal.

## Antes de la clase (una sola vez)

```
pip install -r test/requirements.txt
cd frontend
npm ci
cd ..
```

Para las pruebas contra QA, además:

```
pip install -r test/requirements-qa.txt
python -m playwright install chromium
```

## 1. Las pruebas del módulo, con un comando

```
python "Proyecto Calidad/pruebas/correr_pruebas_web.py"
```

Corre, en este orden, mostrando la salida en vivo:

| Etapa | Qué es | Cantidad | Tiempo aproximado |
|---|---|---|---|
| API (`frontend/api`) | Tests unitarios de la API con pytest, con cobertura de sentencia y decisión | 435 | 45 s |
| Panel (`frontend/src`) | Tests de componentes con Vitest, con cobertura | 382 | 50 s |

Al final imprime un resumen (`OK` o `FALLA` por etapa) y termina con código 0 si todo pasó. La cobertura que muestra
es la de cada herramienta (pytest-cov: 97 % de la API; Vitest: 92,7 % de sentencias del panel); SonarQube Cloud
muestra 97,9 % y 91,9 % porque combina líneas y ramas.

Opciones:

| Comando | Agrega |
|---|---|
| `... correr_pruebas_web.py --smoke` | El smoke contra QA en Render (no necesita clave): servicio vivo y con base, frontend servido, la API exige sesión |
| `... correr_pruebas_web.py --qa` | Smoke, integración y E2E contra QA. Necesita la cuenta de QA en `QA_USUARIO` y `QA_CLAVE` (ver abajo) |
| `... correr_pruebas_web.py --sin-panel` | Solo la API (más rápido) |

Si está definida `TEST_DATABASE_URL` (un Postgres de prueba con `db/schema.sql`), corre también las 10 pruebas del
pool de conexiones contra la base real.

**Si QA estuvo inactivo**, la primera respuesta de Render puede tardar hasta un minuto en despertar el servicio:
conviene abrir `https://optifull-qa.onrender.com` un rato antes.

### Con la cuenta de QA (para `--qa`)

En PowerShell:

```
$env:QA_USUARIO = "usuario_de_qa"
$env:QA_CLAVE = "la_clave"
python "Proyecto Calidad/pruebas/correr_pruebas_web.py" --qa
```

En Git Bash: `QA_USUARIO=... QA_CLAVE=... python "Proyecto Calidad/pruebas/correr_pruebas_web.py" --qa`.

## 2. Mostrar un defecto en rojo y en verde

DEF-002 (la API entregaba el `.env` del servidor). Con el código de antes del arreglo, el test de regresión falla;
con el actual, pasa:

```
git switch --detach 22f4f21
python -m pytest -c test/pytest.ini test/unitarios/test_heatmap.py -k no_sirve_archivos
git switch -
python -m pytest -c test/pytest.ini test/unitarios/test_heatmap.py -k no_sirve_archivos
```

(La primera corrida termina en rojo: así estaba el código cuando se escribió el test. `git switch -` vuelve a la
rama en la que estabas.) El mismo contraste quedó registrado en el pipeline: ejecuciones 39466050826 (rojo) y
39466216477 (verde).

## 3. Un test por tipo, para mostrar uno de cada uno

```
python -m pytest -c test/pytest.ini test/unitarios/test_seguridad.py -v     # seguridad (DEF-023 a DEF-027)
python -m pytest -c test/pytest.ini test/unitarios/test_login.py -k bloque -v   # valores límite del bloqueo
cd frontend && npx vitest run src/components/permisos.test.js && cd ..   # tabla de decisión por rol
```

## 4. Un despliegue nuevo con todo el pipeline

En GitHub: **Actions → Pipeline OptiFull → Run workflow → rama `main` → Run workflow**. Corre todo lo que corre un
push a `main`: build-test, SonarQube Cloud con el quality gate, system-check, deploy a QA, smoke e integración, E2E,
stress y carga sostenida, y el deploy a producción con su smoke. Tarda unos 35 minutos; conviene lanzarlo al
principio de la presentación y volver al final.

## 5. Las pruebas de carga (si las pide)

Tardan 6 minutos (stress) y 10 (sostenida), por eso conviene mostrar el resultado del pipeline. Para correr un
stress corto contra QA, con la cuenta de QA cargada:

```
locust -f test/carga/locustfile.py --headless --host https://optifull-qa.onrender.com -u 20 -r 5 -t 60s --only-summary
```
