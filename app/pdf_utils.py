import os
from io import BytesIO
from datetime import datetime
from flask import current_app
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def format_currency_pdf(amount, currency):
    try:
        formatted = "{:,.2f}".format(float(amount)).replace(',', ' ')
        if formatted.endswith('.00'):
            formatted = formatted[:-3]
    except (ValueError, TypeError):
        return amount
        
    if currency == 'USD':
        return f"${formatted}"
    elif currency == 'HTG':
        return f"{formatted} HTG"
    else:
        return f"{formatted} €"

def generate_transaction_sheet_pdf(transaction):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter, 
        rightMargin=40, 
        leftMargin=40, 
        topMargin=40, 
        bottomMargin=40
    )
    story = []
    
    # Styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=15
    )
    
    section_style = ParagraphStyle(
        'DocSection',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#d97706'),
        spaceBefore=15,
        spaceAfter=8
    )
    
    normal_style = ParagraphStyle(
        'DocNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#334155')
    )
    
    bold_style = ParagraphStyle(
        'DocBold',
        parent=normal_style,
        fontName='Helvetica-Bold'
    )
    
    footer_style = ParagraphStyle(
        'DocFooter',
        parent=styles['Italic'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#64748b'),
        alignment=1 # Centered
    )

    # Header with Logo & Agency Name
    logo_path = os.path.join(current_app.root_path, 'static', 'logo.jpg')
    header_data = []
    
    if os.path.exists(logo_path):
        img = Image(logo_path, width=80, height=50)
        img.hAlign = 'LEFT'
        logo_cell = img
    else:
        logo_cell = Paragraph("<b>CIENTO IMMOBILIER</b>", bold_style)
        
    info_text = f"""<b>CIENTO IMMOBILIER SA</b><br/>
    Gestion Immobilière & Transactions<br/>
    Date : {datetime.now().strftime('%d/%m/%Y à %H:%M')}<br/>
    Réf : {transaction.reference_transaction}
    """
    
    header_data.append([logo_cell, Paragraph(info_text, normal_style)])
    
    header_table = Table(header_data, colWidths=[150, 380])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(header_table)
    
    # Horizontal line
    line_table = Table([[""]], colWidths=[530], rowHeights=[2])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#0f172a')),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 15))
    
    # Document Title
    story.append(Paragraph(f"FICHE DE TRANSACTION OFFICIELLE", title_style))
    story.append(Paragraph(f"Cette fiche récapitule les détails administratifs, financiers et légaux de la transaction commerciale <b>{transaction.reference_transaction}</b>.", normal_style))
    story.append(Spacer(1, 10))
    
    # General Info Table
    story.append(Paragraph("1. Résumé de l'opération", section_style))
    
    # Utilisation de la devise stockée sur la transaction
    currency = transaction.devise or 'EUR'
    
    summary_data = [
        [Paragraph("Référence Transaction :", bold_style), Paragraph(transaction.reference_transaction, normal_style)],
        [Paragraph("Type de Transaction :", bold_style), Paragraph(transaction.type_transaction, normal_style)],
        [Paragraph("Montant de l'opération :", bold_style), Paragraph(format_currency_pdf(transaction.montant, currency), bold_style)],
        [Paragraph("Date de la transaction :", bold_style), Paragraph(transaction.date_transaction.strftime('%d/%m/%Y'), normal_style)],
        [Paragraph("Statut actuel :", bold_style), Paragraph(transaction.statut, normal_style)]
    ]
    
    summary_table = Table(summary_data, colWidths=[180, 350])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))
    
    # Parties Table
    story.append(Paragraph("2. Parties concernées", section_style))
    
    client_name = f"{transaction.client.prenom} {transaction.client.nom}" if transaction.client else "N/A"
    client_contact = f"Tél: {transaction.client.telephone or 'N/A'} | E-mail: {transaction.client.email or 'N/A'}" if transaction.client else ""
    
    owner_name = f"{transaction.propriete.proprietaire.prenom} {transaction.propriete.proprietaire.nom}" if transaction.propriete and transaction.propriete.proprietaire else "N/A"
    owner_contact = f"Tél: {transaction.propriete.proprietaire.telephone or 'N/A'} | E-mail: {transaction.propriete.proprietaire.email or 'N/A'}" if transaction.propriete and transaction.propriete.proprietaire else ""
    
    agent_name = f"{transaction.agent.prenom} {transaction.agent.nom}" if transaction.agent else "N/A"
    agent_role = f"Rôle : {transaction.agent.role}" if transaction.agent else ""
    
    parties_data = [
        [Paragraph("Propriétaire / Vendeur :", bold_style), Paragraph(f"<b>{owner_name}</b><br/>{owner_contact}", normal_style)],
        [Paragraph("Client Acquéreur / Locataire :", bold_style), Paragraph(f"<b>{client_name}</b><br/>{client_contact}", normal_style)],
        [Paragraph("Agent responsable :", bold_style), Paragraph(f"<b>{agent_name}</b><br/>{agent_role}", normal_style)]
    ]
    
    parties_table = Table(parties_data, colWidths=[180, 350])
    parties_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(parties_table)
    story.append(Spacer(1, 10))
    
    # Property details Table
    story.append(Paragraph("3. Description du bien immobilier", section_style))
    
    prop = transaction.propriete
    prop_details = f"<b>{prop.titre}</b><br/>Adresse : {prop.adresse}, {prop.ville}<br/>Type : {prop.type_bien} | Superficie : {prop.superficie or '--'} m²" if prop else "N/A"
    
    prop_data = [
        [Paragraph("Référence du bien :", bold_style), Paragraph(prop.reference_bien if prop else "N/A", normal_style)],
        [Paragraph("Détails physiques :", bold_style), Paragraph(prop_details, normal_style)]
    ]
    
    prop_table = Table(prop_data, colWidths=[180, 350])
    prop_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(prop_table)
    story.append(Spacer(1, 20))
    
    # Signature box
    sig_data = [
        [Paragraph("<b>Signature de l'Agent</b>", bold_style), Paragraph("<b>Signature du Client</b>", bold_style)],
        ["\n\n\n_________________________", "\n\n\n_________________________"]
    ]
    sig_table = Table(sig_data, colWidths=[265, 265])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, 1), 20),
    ]))
    story.append(sig_table)
    
    story.append(Spacer(1, 40))
    # Footer
    story.append(Paragraph("Ciento Immobilier — Document confidentiel généré automatiquement en local.", footer_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_payment_receipt_pdf(payment):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter, 
        rightMargin=45, 
        leftMargin=45, 
        topMargin=45, 
        bottomMargin=45
    )
    story = []
    
    # Styles
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'ReceiptTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=colors.HexColor('#0f172a'),
        alignment=1, # Centered
        spaceAfter=20
    )
    
    normal_style = ParagraphStyle(
        'ReceiptNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=15,
        textColor=colors.HexColor('#334155')
    )
    
    bold_style = ParagraphStyle(
        'ReceiptBold',
        parent=normal_style,
        fontName='Helvetica-Bold'
    )
    
    footer_style = ParagraphStyle(
        'ReceiptFooter',
        parent=styles['Italic'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#64748b'),
        alignment=1
    )

    # Header with Logo & Agency Name
    logo_path = os.path.join(current_app.root_path, 'static', 'logo.jpg')
    header_data = []
    
    if os.path.exists(logo_path):
        img = Image(logo_path, width=80, height=50)
        img.hAlign = 'LEFT'
        logo_cell = img
    else:
        logo_cell = Paragraph("<b>CIENTO IMMOBILIER</b>", bold_style)
        
    info_text = f"""<b>CIENTO IMMOBILIER SA</b><br/>
    Bureau de transaction local<br/>
    Téléphone : +33 1 00 00 00 00<br/>
    E-mail : contact@ciento.immo
    """
    
    header_data.append([logo_cell, Paragraph(info_text, normal_style)])
    
    header_table = Table(header_data, colWidths=[150, 370])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(header_table)
    
    # Horizontal line
    line_table = Table([[""]], colWidths=[520], rowHeights=[1.5])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 25))
    
    # Document Title
    story.append(Paragraph(f"REÇU DE PAIEMENT OFFICIEL", title_style))
    # Utilisation de la devise stockée sur le paiement
    currency = payment.devise or 'EUR'
    client_name = f"{payment.transaction.client.prenom} {payment.transaction.client.nom}" if payment.transaction and payment.transaction.client else "N/A"
    
    # Receipt details
    receipt_text = f"""Le bureau de transaction de Ciento Immobilier certifie par la présente avoir reçu du client <b>{client_name}</b>, le règlement décrit ci-dessous au titre de la transaction <b>{payment.transaction.reference_transaction}</b>.
    """
    story.append(Paragraph(receipt_text, normal_style))
    story.append(Spacer(1, 15))
    
    receipt_data = [
        [Paragraph("Référence Paiement :", bold_style), Paragraph(payment.reference_paiement or f"PAY-{payment.id:05d}", normal_style)],
        [Paragraph("Date du Règlement :", bold_style), Paragraph(payment.date_paiement.strftime('%d/%m/%Y'), normal_style)],
        [Paragraph("Mode de Paiement :", bold_style), Paragraph(payment.mode_paiement, normal_style)],
        [Paragraph("Montant Encaissé :", bold_style), Paragraph(format_currency_pdf(payment.montant, currency), bold_style)],
        [Paragraph("Statut du Règlement :", bold_style), Paragraph(payment.statut, bold_style)]
    ]
    
    receipt_table = Table(receipt_data, colWidths=[180, 340])
    receipt_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(receipt_table)
    story.append(Spacer(1, 20))
    
    # Reference property info
    prop = payment.transaction.propriete if payment.transaction else None
    if prop:
        prop_text = f"<b>Objet de la transaction :</b> {prop.type_bien} réf. <b>{prop.reference_bien}</b> situé à {prop.ville} ({prop.quartier or ''})."
        story.append(Paragraph(prop_text, normal_style))
        
    story.append(Spacer(1, 35))
    
    # Signature box
    sig_data = [
        ["", Paragraph("<b>Pour l'Agence Ciento Immobilier</b>", bold_style)],
        ["", "\n\nCachet & Signature Électronique\nValide en local"]
    ]
    sig_table = Table(sig_data, colWidths=[260, 260])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, 1), 10),
    ]))
    story.append(sig_table)
    
    story.append(Spacer(1, 50))
    
    # Footer
    story.append(Paragraph("Ce reçu de versement est délivré à titre de preuve et ne remplace pas l'acte authentique de vente.", footer_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer
