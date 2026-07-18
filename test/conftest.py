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
