"""Genera informe.pdf a partir de informe.md: Markdown -> HTML con estilos de impresión -> PDF con Edge o Chrome.

Uso (desde esta carpeta):
  pip install markdown
  python generar_pdf.py

Busca Edge o Chrome en las rutas habituales de Windows; con NAVEGADOR=<ruta> se puede indicar otro.
"""
import os
import subprocess
import sys
from pathlib import Path

import markdown

AQUI = Path(__file__).resolve().parent
NAVEGADORES = [
    os.environ.get("NAVEGADOR", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]

ESTILO = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 10pt; line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 24pt; margin: 0 0 6pt; }
h2 { font-size: 15pt; margin: 18pt 0 6pt; padding-bottom: 3pt; border-bottom: 1.5pt solid #2b4c7e; color: #2b4c7e;
     break-after: avoid; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; color: #2b4c7e; break-after: avoid; }
p { margin: 4pt 0 6pt; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.6pt; break-inside: auto; }
tr { break-inside: avoid; }
th { background: #e8eef7; text-align: left; }
th, td { border: 0.6pt solid #b9c4d4; padding: 3pt 5pt; vertical-align: top; }
code { font-family: Consolas, monospace; font-size: 8.6pt; background: #f2f4f7; padding: 0 2pt; }
ul, ol { margin: 4pt 0 6pt 16pt; padding: 0; }
.portada { height: 245mm; display: flex; flex-direction: column; justify-content: center; break-after: page; }
.portada h1 { font-size: 28pt; color: #2b4c7e; border: none; }
.portada h2 { font-size: 15pt; border: none; color: #1a1a1a; margin-bottom: 30pt; }
.portada p { font-size: 11.5pt; margin: 4pt 0; }
"""


def main():
    md = (AQUI / "informe.md").read_text(encoding="utf-8")
    cuerpo = markdown.markdown(md, extensions=["tables", "fenced_code", "md_in_html"])
    html = (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Informe TP Calidad de Software'
            f'</title><style>{ESTILO}</style></head><body>{cuerpo}</body></html>')
    destino_html = AQUI / "informe.html"
    destino_html.write_text(html, encoding="utf-8")
    navegador = next((n for n in NAVEGADORES if n and Path(n).is_file()), None)
    if not navegador:
        sys.exit("No se encontró Edge ni Chrome: abrí informe.html e imprimilo a PDF a mano.")
    import tempfile
    perfil = tempfile.mkdtemp()
    subprocess.run([navegador, "--headless", "--disable-gpu", f"--user-data-dir={perfil}", "--no-pdf-header-footer",
                    f"--print-to-pdf={AQUI / 'informe.pdf'}", destino_html.as_uri()], check=True)
    print("Listo:", AQUI / "informe.pdf")


if __name__ == "__main__":
    main()
