from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, current_app, send_file
from flask_login import login_required, current_user
from app.models import Transaction, Client, Propriete, Utilisateur, Commission, Paiement, Contrat
from app.utils.helpers import log_activity, sanitize_search, role_required
from app import db
from app.services.pdf_service import generate_transaction_sheet_pdf, generate_payment_receipt_pdf
from app.services.excel_service import export_transactions_to_excel
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
import os

transactions = Blueprint('transactions', __name__)

ALLOWED_PDF_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_PDF_EXTENSIONS

@transactions.route('/')
@login_required
@role_required('Comptable', 'Agent immobilier')
def list_transactions():
    search = request.args.get('search', '')
    type_tx = request.args.get('type_transaction', '')
    statut = request.args.get('statut', '')
    
    query = Transaction.query
    
    if search:
        safe_search = sanitize_search(search)
        like_pattern = f'%{safe_search}%'
        query = query.filter(
            (Transaction.reference_transaction.ilike(like_pattern)) |
            (Transaction.observations.ilike(like_pattern))
        )
    if type_tx:
        query = query.filter_by(type_transaction=type_tx)
    if statut:
        query = query.filter_by(statut=statut)
        
    transactions_list = query.order_by(Transaction.date_transaction.desc()).all()
    
    return render_template(
        'transactions/list.html',
        transactions=transactions_list,
        search=search,
        type_transaction=type_tx,
        statut=statut
    )

@transactions.route('/ajouter', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier')
def add_transaction():
    clients = Client.query.order_by(Client.nom.asc()).all()
    proprietes = Propriete.query.filter_by(statut='Disponible').order_by(Propriete.reference_bien.asc()).all()
    agents = Utilisateur.query.filter_by(actif=True).order_by(Utilisateur.nom.asc()).all()
    
    if request.method == 'POST':
        client_id = request.form.get('client_id')
        propriete_id = request.form.get('propriete_id')
        agent_id = request.form.get('agent_id')
        type_transaction = request.form.get('type_transaction')
        montant = request.form.get('montant')
        date_str = request.form.get('date_transaction')
        observations = request.form.get('observations')
        devise = request.form.get('devise', 'EUR')
        
        pourcentage_commission = request.form.get('pourcentage_commission') or 0
        
        try:
            date_transaction = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Format de date invalide.", "danger")
            return redirect(url_for('transactions.add_transaction'))
            
        # Générer une référence unique
        count = Transaction.query.count()
        reference_transaction = f"TX-{datetime.now(timezone.utc).year}-{count + 1:04d}"
        
        new_tx = Transaction(
            reference_transaction=reference_transaction,
            client_id=client_id,
            propriete_id=propriete_id,
            agent_id=agent_id,
            type_transaction=type_transaction,
            montant=montant,
            date_transaction=date_transaction,
            statut='En cours',
            observations=observations,
            devise=devise
        )
        
        try:
            db.session.add(new_tx)
            db.session.flush() # Récupérer l'ID généré pour la commission
            
            # Calcul et création de la commission associée (seulement si agent affecté)
            pct = float(pourcentage_commission)
            if agent_id and pct > 0:
                mt_commission = float(montant) * (pct / 100)
                
                commission = Commission(
                    transaction_id=new_tx.id,
                    agent_id=agent_id,
                    pourcentage=pct,
                    montant=mt_commission,
                    date_calcul=date_transaction
                )
                db.session.add(commission)
            
            # Réserver la propriété (changer son statut en "Réservé")
            prop = db.session.get(Propriete, propriete_id)
            if prop:
                prop.statut = 'Réservé'
                
            db.session.commit()
            log_activity(current_user.id, f"Création transaction: {reference_transaction}", "transactions", new_tx.id)
            flash(f"La transaction {reference_transaction} a été enregistrée. Le bien est désormais réservé.", "success")
            return redirect(url_for('transactions.view_transaction', tx_id=new_tx.id))
        except Exception as e:
            db.session.rollback()
            flash("Erreur lors de l'enregistrement. Veuillez réessayer.", "danger")
            
    return render_template(
        'transactions/form.html',
        clients=clients,
        proprietes=proprietes,
        agents=agents
    )

@transactions.route('/details/<int:tx_id>')
@login_required
@role_required('Comptable', 'Agent immobilier')
def view_transaction(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    # Récupérer la commission
    commission = Commission.query.filter_by(transaction_id=tx.id).first()
    return render_template('transactions/view.html', tx=tx, commission=commission)

@transactions.route('/finaliser/<int:tx_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def finalize_transaction(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    
    if tx.statut == 'Finalisée':
        flash("La transaction est déjà finalisée.", "info")
        return redirect(url_for('transactions.view_transaction', tx_id=tx_id))
        
    try:
        tx.statut = 'Finalisée'
        
        # Mettre à jour le statut du bien en fonction du type d'opération
        prop = tx.propriete
        if prop:
            if tx.type_transaction == 'Vente':
                prop.statut = 'Vendu'
            elif tx.type_transaction == 'Location':
                prop.statut = 'Loué'
                
        db.session.commit()
        log_activity(current_user.id, f"Finalisation transaction: {tx.reference_transaction}", "transactions", tx.id)
        flash(f"La transaction {tx.reference_transaction} a été finalisée. Le bien est désormais marqué comme {prop.statut}.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de la finalisation. Veuillez réessayer.", "danger")
        
    return redirect(url_for('transactions.view_transaction', tx_id=tx_id))

@transactions.route('/supprimer/<int:tx_id>', methods=['POST'])
@login_required
def delete_transaction(tx_id):
    if current_user.role not in ['Administrateur', 'Directeur']:
        abort(403)
        
    tx = Transaction.query.get_or_404(tx_id)
    ref = tx.reference_transaction
    
    # Libérer la propriété associée (remettre à "Disponible")
    prop = tx.propriete
    if prop and prop.statut in ['Réservé', 'Vendu', 'Loué']:
        prop.statut = 'Disponible'
        
    try:
        db.session.delete(tx)
        db.session.commit()
        log_activity(current_user.id, f"Suppression transaction: {ref}", "transactions", tx_id)
        flash(f"La transaction {ref} a été supprimée. La propriété est de nouveau disponible.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de la suppression. Veuillez réessayer.", "danger")
        
    return redirect(url_for('transactions.list_transactions'))

@transactions.route('/export')
@login_required
@role_required('Comptable', 'Agent immobilier')
def export_transactions():
    search = request.args.get('search', '')
    type_tx = request.args.get('type_transaction', '')
    statut = request.args.get('statut', '')
    
    query = Transaction.query
    
    if search:
        safe_search = sanitize_search(search)
        like_pattern = f'%{safe_search}%'
        query = query.filter(
            (Transaction.reference_transaction.ilike(like_pattern)) |
            (Transaction.observations.ilike(like_pattern))
        )
    if type_tx:
        query = query.filter_by(type_transaction=type_tx)
    if statut:
        query = query.filter_by(statut=statut)
        
    transactions_list = query.order_by(Transaction.date_transaction.desc()).all()
    
    output = export_transactions_to_excel(transactions_list)
    log_activity(current_user.id, "Export des transactions", "transactions")
    
    return send_file(
        output,
        download_name=f"transactions_{datetime.now(timezone.utc).strftime('%Y%m%d')}.xlsx",
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@transactions.route('/modifier/<int:tx_id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(tx_id):
    if current_user.role not in ['Administrateur', 'Directeur']:
        abort(403)
        
    tx = Transaction.query.get_or_404(tx_id)
    clients = Client.query.order_by(Client.nom.asc()).all()
    # On affiche les biens disponibles OU le bien déjà associé à la transaction
    proprietes = Propriete.query.filter((Propriete.statut == 'Disponible') | (Propriete.id == tx.propriete_id)).order_by(Propriete.reference_bien.asc()).all()
    agents = Utilisateur.query.filter_by(actif=True).order_by(Utilisateur.nom.asc()).all()
    
    commission = Commission.query.filter_by(transaction_id=tx.id).first()
    
    if request.method == 'POST':
        tx.client_id = request.form.get('client_id')
        
        nouveau_propriete_id = request.form.get('propriete_id')
        if int(nouveau_propriete_id) != tx.propriete_id:
            # Libérer l'ancienne propriété
            ancienne_prop = db.session.get(Propriete, tx.propriete_id)
            if ancienne_prop and ancienne_prop.statut in ['Réservé', 'Vendu', 'Loué']:
                ancienne_prop.statut = 'Disponible'
            
            # Réserver la nouvelle
            nouvelle_prop = db.session.get(Propriete, int(nouveau_propriete_id))
            if nouvelle_prop:
                nouvelle_prop.statut = 'Réservé'
            
            tx.propriete_id = nouveau_propriete_id

        tx.agent_id = request.form.get('agent_id')
        tx.type_transaction = request.form.get('type_transaction')
        tx.montant = request.form.get('montant')
        date_str = request.form.get('date_transaction')
        tx.observations = request.form.get('observations')
        tx.devise = request.form.get('devise', 'EUR')
        
        pourcentage_commission = request.form.get('pourcentage_commission') or 0
        
        try:
            tx.date_transaction = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Format de date invalide.", "danger")
            return redirect(url_for('transactions.edit_transaction', tx_id=tx.id))
            
        try:
            # Update commission
            pct = float(pourcentage_commission)
            mt_commission = float(tx.montant) * (pct / 100)
            
            if commission:
                commission.pourcentage = pct
                commission.montant = mt_commission
                commission.agent_id = tx.agent_id
            else:
                commission = Commission(
                    transaction_id=tx.id,
                    agent_id=tx.agent_id,
                    pourcentage=pct,
                    montant=mt_commission,
                    date_calcul=tx.date_transaction
                )
                db.session.add(commission)
                
            db.session.commit()
            log_activity(current_user.id, f"Modification transaction: {tx.reference_transaction}", "transactions", tx.id)
            flash(f"La transaction {tx.reference_transaction} a été modifiée avec succès.", "success")
            return redirect(url_for('transactions.view_transaction', tx_id=tx.id))
        except Exception as e:
            db.session.rollback()
            flash("Erreur lors de la modification. Veuillez réessayer.", "danger")
            
    return render_template(
        'transactions/form.html',
        tx=tx,
        commission=commission,
        clients=clients,
        proprietes=proprietes,
        agents=agents
    )

# --- Ajouter un paiement ---
@transactions.route('/paiement/ajouter/<int:tx_id>', methods=['POST'])
@login_required
@role_required('Comptable', 'Agent immobilier')
def add_payment(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    montant = request.form.get('montant')
    mode_paiement = request.form.get('mode_paiement')
    reference_paiement = request.form.get('reference_paiement')
    date_str = request.form.get('date_paiement')
    devise = request.form.get('devise', 'EUR')
    
    try:
        date_paiement = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        flash("Format de date invalide.", "danger")
        return redirect(url_for('transactions.view_transaction', tx_id=tx_id))
        
    new_pay = Paiement(
        transaction_id=tx_id,
        montant=montant,
        mode_paiement=mode_paiement,
        reference_paiement=reference_paiement,
        date_paiement=date_paiement,
        statut='Validé',
        devise=devise
    )
    
    try:
        db.session.add(new_pay)
        db.session.commit()
        log_activity(current_user.id, f"Encaissement paiement transaction {tx.reference_transaction}", "paiements", new_pay.id)
        flash("Le paiement a été enregistré avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de l'ajout du paiement. Veuillez réessayer.", "danger")
        
    return redirect(url_for('transactions.view_transaction', tx_id=tx_id))

# --- Ajouter un contrat PDF ---
@transactions.route('/contrat/ajouter/<int:tx_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def add_contract(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    numero_contrat = request.form.get('numero_contrat')
    date_sig_str = request.form.get('date_signature')
    date_deb_str = request.form.get('date_debut') or None
    date_fin_str = request.form.get('date_fin') or None
    
    if 'contrat_pdf' not in request.files:
        flash("Fichier contrat PDF manquant.", "warning")
        return redirect(url_for('transactions.view_transaction', tx_id=tx_id))
        
    file = request.files['contrat_pdf']
    
    try:
        date_signature = datetime.strptime(date_sig_str, "%Y-%m-%d").date()
        date_debut = datetime.strptime(date_deb_str, "%Y-%m-%d").date() if date_deb_str else None
        date_fin = datetime.strptime(date_fin_str, "%Y-%m-%d").date() if date_fin_str else None
    except ValueError:
        flash("Erreur dans les formats de dates.", "danger")
        return redirect(url_for('transactions.view_transaction', tx_id=tx_id))
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"CONTRAT_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'documents', unique_filename)
        
        file.save(filepath)
        
        rel_path = f"uploads/documents/{unique_filename}"
        
        new_contrat = Contrat(
            transaction_id=tx_id,
            numero_contrat=numero_contrat,
            date_signature=date_signature,
            date_debut=date_debut,
            date_fin=date_fin,
            fichier_pdf=rel_path
        )
        
        try:
            db.session.add(new_contrat)
            db.session.commit()
            log_activity(current_user.id, f"Ajout contrat {numero_contrat} pour transaction {tx.reference_transaction}", "contrats", new_contrat.id)
            flash("Le contrat a été enregistré et téléversé.", "success")
        except Exception as e:
            db.session.rollback()
            flash("Erreur lors de l'enregistrement du contrat. Veuillez réessayer.", "danger")
    else:
        flash("Seuls les fichiers PDF sont autorisés pour les contrats.", "danger")
        
    return redirect(url_for('transactions.view_transaction', tx_id=tx_id))

@transactions.route('/recu/<int:tx_id>')
@login_required
@role_required('Comptable', 'Agent immobilier')
def download_transaction_pdf(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    pdf_buffer = generate_transaction_sheet_pdf(tx)
    log_activity(current_user.id, f"Génération PDF Fiche Transaction {tx.reference_transaction}", "transactions", tx.id)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Fiche_Transaction_{tx.reference_transaction}.pdf"
    )

@transactions.route('/paiement/recu/<int:pay_id>')
@login_required
@role_required('Comptable', 'Agent immobilier')
def download_payment_receipt_pdf_route(pay_id):
    payment = Paiement.query.get_or_404(pay_id)
    pdf_buffer = generate_payment_receipt_pdf(payment)
    log_activity(current_user.id, f"Génération PDF Reçu Paiement {payment.id}", "paiements", payment.id)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Recu_Paiement_{payment.id}.pdf"
    )
