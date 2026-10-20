"""Deja importables los modulos de OptiFull desde los tests, sin necesidad de
paquetizar 'frontend/' ni cambiar el cwd: agrega la raiz del repo (para
'deteccion.*') y 'frontend/' (para 'api', que no es un paquete) a sys.path."""
import sys
from pathlib import Path

ROOT     = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

for p in (ROOT, FRONTEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


# ── Base de datos falsa compartida ───────────────────────────────────────────
# Reemplaza la conexion a Supabase en los tests de la API: cada consulta se
# responde con las filas de la primera regla cuyo fragmento aparece en el SQL.
# Asi un test declara solo los datos que le importan, sin conectarse a nada.
import copy  # noqa: E402

import pytest  # noqa: E402


class CursorFalso:
    def __init__(self, bd):
        self.bd, self._filas = bd, []
        self.rowcount = bd.rowcount   # filas afectadas por un UPDATE
        self.connection = bd

    def execute(self, sql, params=None):
        self.bd.consultas.append((sql, params))
        if self.bd.error:
            raise self.bd.error
        for fragmento, filas in self.bd.reglas:
            if fragmento in sql:
                self._filas = copy.deepcopy(filas)   # el codigo puede modificar las filas que recibe
                return
        self._filas = []

    def fetchall(self):
        return self._filas

    def fetchone(self):
        return self._filas[0] if self._filas else None

    def close(self):
        pass


class BDFalsa:
    """Conexion falsa: bd.responder('FROM camaras', [...]) define que devuelve cada consulta."""

    def __init__(self):
        self.reglas, self.consultas = [], []
        self.error = None   # si se setea, toda consulta lanza esta excepcion
        self.rowcount = 1   # lo que devuelve cursor.rowcount (0 = el UPDATE no encontro la fila)
        self.commits = self.rollbacks = 0
        self.cerrada = False

    def responder(self, fragmento_sql, filas):
        self.reglas.append((fragmento_sql, filas))
        return self

    def cursor(self, cursor_factory=None):
        return CursorFalso(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.cerrada = True


@pytest.fixture
def bd():
    return BDFalsa()


# ── Sesion iniciada por defecto ──────────────────────────────────────────────
# La API exige una sesion (frontend/api/sesion.py). Los tests de cada endpoint corren como un
# administrador logueado; los tests de la sesion en si (test_sesion.py) usan @pytest.mark.sin_sesion
# para probar el mecanismo real de la cookie.
ADMIN_DE_PRUEBA = {"id": 1, "usuario": "admin_test", "rol": "administrador", "dur": 3600}


@pytest.fixture(autouse=True)
def sesion_de_prueba(request, monkeypatch):
    if request.node.get_closest_marker("sin_sesion"):
        return
    for nombre in ("api.sesion", "frontend.api.sesion"):
        modulo = sys.modules.get(nombre)
        if modulo is not None:
            monkeypatch.setattr(modulo, "usuario_de_request", lambda: dict(ADMIN_DE_PRUEBA))
