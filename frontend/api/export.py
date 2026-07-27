"""Exportacion del reporte de permanencia a CSV y PDF."""
import csv
import io
from datetime import datetime

from flask import Response, jsonify

from .blueprint import api_bp
from .db import cargar_csv, cargar_db, cargar_permanencias_db
from .stats import calcular_stats


@api_bp.route('/export/csv')
def export_csv():
    rows   = cargar_db()
    fuente = 'db' if rows is not None else 'csv'
    if rows is None:
        try:
            rows = cargar_csv()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    permanencias = cargar_permanencias_db() if fuente == 'db' else None
    stats = calcular_stats(rows, permanencias)
    detalle = permanencias if permanencias is not None else rows
    buf = io.StringIO()
    w   = csv.writer(buf)

    # Encabezado con resumen
    w.writerow(['# OptiFull — Reporte de Permanencia'])
    w.writerow([f'# Generado: {datetime.now().strftime("%d/%m/%Y %H:%M")}'])
    w.writerow([f'# Fuente: {"Base de datos" if fuente == "db" else "CSV local"}'])
    w.writerow([])
    w.writerow(['## Resumen'])
    w.writerow(['Personas totales', stats['personas_totales']])
    w.writerow(['Personas unicas', stats['personas_unicas']])
    w.writerow(['Permanencia promedio (min)', stats['permanencia_promedio_min']])
    w.writerow(['Permanencia maxima (min)', stats['permanencia_maxima_min']])
    w.writerow(['Permanencia minima valida (min)', stats['permanencia_minima_valida_min']])
    w.writerow([])
    w.writerow(['## Distribucion'])
    w.writerow(['Rango', 'Cantidad'])
    for d in stats['distribucion']:
        w.writerow([d['rango'], d['count']])
    w.writerow([])

    # Detalle por persona (1 fila = 1 cliente real, con permanencia ya sumada
    # entre sesiones/huecos si la fuente es la BD; ver cargar_permanencias_db)
    w.writerow(['## Detalle por persona'])
    w.writerow(['ID', 'Entrada', 'Salida', 'Duracion (seg)', 'Duracion (min)'])
    for r in detalle:
        w.writerow([r.get('cliente_id', r.get('id')), r['entrada'], r['salida'],
                    r['duracion_seg'], r['duracion_min']])

    fname = f'optifull_reporte_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    return Response(
        buf.getvalue().encode('utf-8-sig'),   # utf-8-sig para que Excel lo abra bien
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'}
    )


@api_bp.route('/export/pdf')
def export_pdf():
    rows      = cargar_db()
    es_db     = rows is not None
    if rows is None:
        try:
            rows = cargar_csv()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    permanencias = cargar_permanencias_db() if es_db else None
    stats  = calcular_stats(rows, permanencias)
    fuente = 'Base de datos' if es_db else 'CSV local'

    from fpdf import FPDF

    def t(s):
        """Elimina caracteres fuera del rango latin-1 que fpdf no soporta."""
        return s.replace('—', '-').replace('–', '-').encode('latin-1', 'replace').decode('latin-1')

    class PDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 14)
            self.set_text_color(37, 99, 168)
            self.cell(0, 10, t('OptiFull - Reporte de Permanencia'), align='L')
            self.set_font('Helvetica', '', 9)
            self.set_text_color(120, 120, 120)
            self.cell(0, 10, datetime.now().strftime('%d/%m/%Y  %H:%M'), align='R')
            self.ln(4)
            self.set_draw_color(220, 220, 220)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(6)

        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, t(f'Pagina {self.page_no()}  -  Fuente: {fuente}'), align='C')

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # ── KPIs ──
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, t('Resumen estadistico'), ln=True)
    pdf.ln(2)

    kpis = [
        ('Personas analizadas',          f"{stats['personas_totales']} registros"),
        ('Personas unicas',               f"{stats['personas_unicas']}"),
        ('Permanencia promedio',          f"{stats['permanencia_promedio_min']} min"),
        ('Permanencia maxima',            f"{stats['permanencia_maxima_min']} min"),
        ('Permanencia minima valida',     f"{stats['permanencia_minima_valida_min']} min"),
        ('Registros validos (> 0.5 min)', f"{stats['personas_validas']}"),
    ]
    pdf.set_font('Helvetica', '', 10)
    for label, val in kpis:
        pdf.set_text_color(80, 80, 80)
        pdf.cell(90, 7, t(label))
        pdf.set_text_color(30, 30, 30)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(0, 7, t(val), ln=True)
        pdf.set_font('Helvetica', '', 10)

    # ── Distribución ──
    pdf.ln(6)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, t('Distribucion de permanencia'), ln=True)
    pdf.ln(2)

    pdf.set_fill_color(245, 247, 250)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(80, 7, 'Rango', border='B', fill=True)
    pdf.cell(40, 7, 'Personas', border='B', fill=True, align='C')
    pdf.ln()

    pdf.set_font('Helvetica', '', 10)
    total = stats['personas_totales'] or 1
    for d in stats['distribucion']:
        pct = round(d['count'] / total * 100, 1)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(80, 7, d['rango'])
        pdf.cell(40, 7, f"{d['count']}  ({pct}%)", align='C')
        pdf.ln()

    # ── Tabla detalle ──
    pdf.ln(6)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, t('Detalle por persona'), ln=True)
    pdf.ln(2)

    pdf.set_fill_color(245, 247, 250)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(60, 60, 60)
    for col, w in [('ID', 15), ('Entrada', 40), ('Salida', 40), ('Seg.', 30), ('Min.', 30)]:
        pdf.cell(w, 7, col, border='B', fill=True, align='C')
    pdf.ln()

    pdf.set_font('Helvetica', '', 9)
    for i, r in enumerate(rows):
        if i % 2 == 0:
            pdf.set_fill_color(250, 251, 253)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(15, 6.5, str(r['id']),          fill=True, align='C')
        pdf.cell(40, 6.5, str(r['entrada']),      fill=True, align='C')
        pdf.cell(40, 6.5, str(r['salida']),       fill=True, align='C')
        pdf.cell(30, 6.5, str(r['duracion_seg']), fill=True, align='C')
        pdf.cell(30, 6.5, str(r['duracion_min']), fill=True, align='C')
        pdf.ln()

    buf  = io.BytesIO(pdf.output())
    fname = f'optifull_reporte_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf'
    return Response(
        buf.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{fname}"'}
    )
