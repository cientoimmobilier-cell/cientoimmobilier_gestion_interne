"""
Exports de donnees du module Sauvegarde Cloud : rapports CSV / Excel / PDF
et dump SQL complet de la base (schema + donnees, portables sqlite/postgres).
"""
import base64
import csv
import io
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from sqlalchemy import JSON as SAJSON, select

from app import db
from app.models import (
    BienAirbnb, Client, Contrat, Occupation, Proprietaire,
    Propriete, Transaction, Utilisateur,
)
from app.utils.helpers import neutralize_formula

REPORT_GROUPS = {
    'clients': {'model': Client, 'label': 'Clients'},
    'proprietaires': {'model': Proprietaire, 'label': 'Propriétaires'},
    'biens': {'model': Propriete, 'label': 'Biens immobiliers'},
    'contrats': {'model': Contrat, 'label': 'Contrats'},
    'transactions': {'model': Transaction, 'label': 'Transactions'},
    'occupations': {'model': Occupation, 'label': 'Occupations'},
    'airbnb': {'model': BienAirbnb, 'label': 'Biens Airbnb'},
    'utilisateurs': {'model': Utilisateur, 'label': 'Utilisateurs'},
}


def _prettify(name):
    return re.sub(r'_+', ' ', name).replace(' id', ' n°').strip().title()


def _esc_pdf(value):
    """Échappe les balises mini-HTML interprétées par ReportLab."""
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _serialize(value):
    if value is None:
        return ''
    if isinstance(value, (datetime, date)):
        return value.strftime('%d/%m/%Y %H:%M') if isinstance(value, datetime) else value.strftime('%d/%m/%Y')
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        return 'Oui' if value else 'Non'
    if isinstance(value, bytes):
        return base64.b64encode(value).decode('ascii')
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _rows(group_key):
    group = REPORT_GROUPS[group_key]
    return db.session.execute(select(group['model'])).scalars().all()


def export_csv(group_key):
    group = REPORT_GROUPS[group_key]
    columns = list(group['model'].__table__.columns)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    writer.writerow([_prettify(c.name) for c in columns])
    for obj in _rows(group_key):
        writer.writerow([
            neutralize_formula(_serialize(getattr(obj, c.name))) for c in columns
        ])
    return buffer.getvalue().encode('utf-8-sig')


def export_excel(group_key):
    group = REPORT_GROUPS[group_key]
    columns = list(group['model'].__table__.columns)
    wb = Workbook()
    ws = wb.active
    ws.title = group['label'][:31]
    ws.append([_prettify(c.name) for c in columns])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for obj in _rows(group_key):
        ws.append([
            neutralize_formula(_serialize(getattr(obj, c.name))) for c in columns
        ])
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def export_pdf(group_key):
    group = REPORT_GROUPS[group_key]
    columns = list(group['model'].__table__.columns)
    rows = _rows(group_key)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        rightMargin=28, leftMargin=28, topMargin=40, bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CielTitle', parent=styles['Title'], fontSize=16,
        textColor=colors.HexColor('#0f172a'), spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        'CielSub', parent=styles['Normal'], fontSize=9,
        textColor=colors.HexColor('#64748b'), spaceAfter=10,
    )
    cell_style = ParagraphStyle(
        'CielCell', parent=styles['Normal'], fontSize=7, leading=9,
    )
    header_style = ParagraphStyle(
        'CielHeader', parent=styles['Normal'], fontSize=7.5, leading=9,
        fontName='Helvetica-Bold', textColor=colors.white,
    )

    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawCentredString(A4[1] / 2, 18, f'CIENTO IMMOBILIER — Page {_doc.page}')
        canvas.restoreState()

    story = [
        Paragraph('CIENTO IMMOBILIER', title_style),
        Paragraph(
            f'{group["label"]} — {len(rows)} enregistrement(s) — '
            f'{datetime.now(timezone.utc).strftime("%d/%m/%Y à %H:%M")} UTC', sub_style),
    ]
    data = [[Paragraph(_prettify(c.name), header_style) for c in columns]]
    for obj in rows:
        data.append([
            Paragraph(_esc_pdf(_serialize(getattr(obj, c.name))), cell_style)
            for c in columns
        ])

    if rows:
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f1f5f9')]),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#cbd5e1')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(table)
    else:
        story.append(Paragraph('Aucune donnée.', sub_style))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _ident(name):
    if name.islower() and name.isidentifier():
        return name
    return f'"{name}"'


def _sql_literal(value, dialect_name):
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Decimal):
        # str() conserve la précision exacte du NUMERIC ; repr(float())
        # perdait les décimales au-delà de 15-16 chiffres significatifs.
        return str(value)
    if isinstance(value, bytes):
        hexed = value.hex()
        if dialect_name == 'postgresql':
            return f"'\\x{hexed}'"
        return f"X'{hexed}'"
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime) and value.tzinfo is not None:
            # Les colonnes sont TIMESTAMP sans fuseau : on dumps en UTC naïf
            # pour éviter un décalage à la restauration.
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return "'" + value.isoformat().replace("'", "''") + "'"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return "'" + str(value).replace("'", "''") + "'"


def export_sql():
    """Dump complet : BEGIN, DROP (ordre inverse), CREATE, INSERT, sequences."""
    dialect_name = db.engine.dialect.name
    tables = list(db.metadata.sorted_tables)
    lines = [
        '-- CIENTO IMMOBILIER — Sauvegarde de la base de données',
        f'-- Générée le {datetime.now(timezone.utc).strftime("%d/%m/%Y à %H:%M")} UTC',
        'BEGIN;',
    ]
    for table in reversed(tables):
        if dialect_name == 'sqlite':
            lines.append(f'DROP TABLE IF EXISTS {_ident(table.name)};')
        else:
            lines.append(f'DROP TABLE IF EXISTS {_ident(table.name)} CASCADE;')
    for table in tables:
        from sqlalchemy.schema import CreateTable
        lines.append(str(CreateTable(table).compile(dialect=db.engine.dialect)) + ';')
        rows = db.session.execute(select(table)).mappings().all()
        for row in rows:
            columns = [c.name for c in table.columns]
            values = ', '.join(_sql_literal(row[c], dialect_name) for c in columns)
            lines.append(
                f'INSERT INTO {_ident(table.name)} '
                f'({", ".join(_ident(c) for c in columns)}) VALUES ({values});'
            )
    if dialect_name == 'postgresql':
        for table in tables:
            int_pk = next((c for c in table.columns if c.primary_key), None)
            if int_pk is not None:
                lines.append(
                    f"SELECT setval(pg_get_serial_sequence('{table.name}', '{int_pk.name}'), "
                    f"COALESCE((SELECT MAX({_ident(int_pk.name)}) FROM {_ident(table.name)}), 1));"
                )
    lines.append('COMMIT;')
    return '\n'.join(lines)

