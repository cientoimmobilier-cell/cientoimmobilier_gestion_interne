import logging
import traceback
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, current_app, send_file
from flask_login import login_required, current_user
from app.models import Transaction, Client, Propriete, Utilisateur, Commission, Paiement, Contrat
from app.utils.helpers import log_activity, sanitize_search, role_required
from app.utils.upload_security import (
    validate_and_save_upload, UploadValidationError, ALLOWED_PDFS
)
from app import db
from sqlalchemy import select, func as sa_func
from sqlalchemy.orm import joinedload
from app.services.pdf_service import generate_transaction_sheet_pdf, generate_payment_receipt_pdf
from app.services.excel_service import export_transactions_to_excel
from datetime import datetime, timezone, date
import os

logger = logging.getLogger(__name__)

transactions = Blueprint('transactions', __name__)

@transactions.route('/')
@login_required
@role_required('Comptable', 'Agent immobilier')
def list_transactions():
    search = request.args.get('search', '')
    type_tx = request.args.get('type_transaction', '')
    statut = request.args.get('statut', '')
    sort = request.args.get('sort', 'date_transaction')
    order = request.args.get('order', 'desc')
    per_page = request.args.get('per_page', 20, type=int)

    stmt = select(Transaction)

    if search:
        safe_search = sanitize_search(search)
        like_pattern = f'%{safe_search}%'
        stmt = stmt.where(
            (Transaction.reference_transaction.ilike(like_pattern)) |
            (Transaction.observations.ilike(like_pattern))
        )
    if type_tx:
        stmt = stmt.where(Transaction.type_transaction == type_tx)
    if statut:
        stmt = stmt.where(Transaction.statut == statut)

    page = request.args.get('page', 1, type=int)
    sort_column = getattr(Transaction, sort, None)
    if sort_column is None:
        sort_column = Transaction.date_transaction
        order = 'desc'
    stmt = stmt.options(
        joinedload(Transaction.client),
        joinedload(Transaction.propriete),
        joinedload(Transaction.agent)
    ).order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    transactions_list = pagination.items

    return render_template(
        'transactions/list.html',
        transactions=transactions_list,
        pagination=pagination,
        search=search,
        type_transaction=type_tx,
        statut=statut,
        sort=sort,
        order=order,
        per_page=per_page
    )

@transactions.route('/ajouter', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier')
def add_transaction():
    clients = db.session.execute(select(Client).order_by(Client.nom.asc())).scalars().all()
    proprietes = db.session.execute(select(Propriete).where(Propriete.statut == 'Disponible').order_by(Propriete.reference_bien.asc())).scalars().all()
    agents = db.session.execute(select(Utilisateur).where(Utilisateur.actif == True).order_by(Utilisateur.nom.asc())).scalars().all()
    
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
        except (ValueError, TypeError):
            flash("Format de date invalide. Utilisez le format AAAA-MM-JJ.", "danger")
            return redirect(url_for('transactions.add_transaction'))

        if date_transaction > date.today():
            flash("La date de transaction ne peut pas être dans le futur.", "danger")
            return redirect(url_for('transactions.add_transaction'))
            
        # Générer une référence unique
        count = db.session.execute(select(sa_func.count(Transaction.id))).scalar()
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
            
            # Réserver la propriété (changer son statut en "Réservé").
            # Vérification côté serveur : le filtre "Disponible" du formulaire
            # peut être périmé (double réservation) ou contourné par POST.
            prop = db.session.get(Propriete, propriete_id)
            if prop is None:
                db.session.rollback()
                flash("La propriété sélectionnée est introuvable.", "danger")
                return redirect(url_for('transactions.add_transaction'))
            if prop.statut != 'Disponible':
                db.session.rollback()
                flash(
                    f"Le bien {prop.reference_bien} n'est plus disponible "
                    f"(statut actuel : {prop.statut}).", "warning")
                return redirect(url_for('transactions.add_transaction'))
            prop.statut = 'Réservé'
                
            log_activity(current_user.id, f"Création transaction: {reference_transaction}", "transactions", new_tx.id)
            db.session.commit()
            flash(f"La transaction {reference_transaction} a été enregistrée. Le bien est désormais réservé.", "success")
            return redirect(url_for('transactions.view_transaction', tx_id=new_tx.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"[TRANSACTIONS] Échec création par user_id={current_user.id}: {e}")
            logger.error(traceback.format_exc())
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
    tx = db.session.get(Transaction, tx_id)
    if tx is None:
        abort(404)
    # Récupérer la commission
    commission = db.session.execute(select(Commission).where(Commission.transaction_id == tx.id)).scalars().first()
    return render_template('transactions/view.html', tx=tx, commission=commission)

@transactions.route('/finaliser/<int:tx_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def finalize_transaction(tx_id):
    tx = db.session.get(Transaction, tx_id)
    if tx is None:
        abort(404)
    
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
                
        log_activity(current_user.id, f"Finalisation transaction: {tx.reference_transaction}", "transactions", tx.id)
        db.session.commit()
        flash(f"La transaction {tx.reference_transaction} a été finalisée. Le bien est désormais marqué comme {prop.statut}.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[TRANSACTIONS] Échec finalisation tx_id={tx_id} par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la finalisation. Veuillez réessayer.", "danger")
        
    return redirect(url_for('transactions.view_transaction', tx_id=tx_id))

@transactions.route('/supprimer/<int:tx_id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def delete_transaction(tx_id):
    tx = db.session.get(Transaction, tx_id)
    if tx is None:
        abort(404)
    ref = tx.reference_transaction
    
    # Libérer la propriété associée (remettre à "Disponible")
    prop = tx.propriete
    if prop and prop.statut in ['Réservé', 'Vendu', 'Loué']:
        prop.statut = 'Disponible'
        
    try:
        db.session.delete(tx)
        log_activity(current_user.id, f"Suppression transaction: {ref}", "transactions", tx_id)
        db.session.commit()
        flash(f"La transaction {ref} a été supprimée. La propriété est de nouveau disponible.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[TRANSACTIONS] Échec suppression tx_id={tx_id} par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la suppression. Veuillez réessayer.", "danger")
        
    return redirect(url_for('transactions.list_transactions'))

@transactions.route('/export', methods=['POST'])
@login_required
@role_required('Comptable', 'Agent immobilier')
def export_transactions():
    search = request.form.get('search', '')
    type_tx = request.form.get('type_transaction', '')
    statut = request.form.get('statut', '')
    
    stmt = select(Transaction)
    
    if search:
        safe_search = sanitize_search(search)
        like_pattern = f'%{safe_search}%'
        stmt = stmt.where(
            (Transaction.reference_transaction.ilike(like_pattern)) |
            (Transaction.observations.ilike(like_pattern))
        )
    if type_tx:
        stmt = stmt.where(Transaction.type_transaction == type_tx)
    if statut:
        stmt = stmt.where(Transaction.statut == statut)
        
    stmt = stmt.options(
        joinedload(Transaction.client),
        joinedload(Transaction.propriete),
        joinedload(Transaction.agent)
    ).order_by(Transaction.date_transaction.desc())
    transactions_list = db.session.execute(stmt).scalars().all()
    
    try:
        output = export_transactions_to_excel(transactions_list)
        log_activity(current_user.id, "Export des transactions", "transactions")
        db.session.commit()
        return send_file(
            output,
            download_name=f"transactions_{datetime.now(timezone.utc).strftime('%Y%m%d')}.xlsx",
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"[TRANSACTIONS] Échec export Excel par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'exportation. Veuillez réessayer.", "danger")
        return redirect(url_for('transactions.list_transactions'))

@transactions.route('/modifier/<int:tx_id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def edit_transaction(tx_id):
    tx = db.session.get(Transaction, tx_id)
    if tx is None:
        abort(404)
    clients = db.session.execute(select(Client).order_by(Client.nom.asc())).scalars().all()
    # On affiche les biens disponibles OU le bien déjà associé à la transaction
    proprietes = db.session.execute(select(Propriete).where(
        (Propriete.statut == 'Disponible') | (Propriete.id == tx.propriete_id)
    ).order_by(Propriete.reference_bien.asc())).scalars().all()
    agents = db.session.execute(select(Utilisateur).where(Utilisateur.actif == True).order_by(Utilisateur.nom.asc())).scalars().all()
    
    commission = db.session.execute(select(Commission).where(Commission.transaction_id == tx.id)).scalars().first()
    
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
            if nouvelle_prop is None:
                db.session.rollback()
                flash("La nouvelle propriété est introuvable.", "danger")
                return redirect(url_for('transactions.edit_transaction', tx_id=tx.id))
            if nouvelle_prop.statut != 'Disponible':
                db.session.rollback()
                flash(
                    f"Le bien {nouvelle_prop.reference_bien} n'est plus disponible "
                    f"(statut actuel : {nouvelle_prop.statut}).", "warning")
                return redirect(url_for('transactions.edit_transaction', tx_id=tx.id))
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
        except (ValueError, TypeError):
            flash("Format de date invalide.", "danger")
            return redirect(url_for('transactions.edit_transaction', tx_id=tx.id))

        if tx.date_transaction > date.today():
            flash("La date de transaction ne peut pas être dans le futur.", "danger")
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
                
            log_activity(current_user.id, f"Modification transaction: {tx.reference_transaction}", "transactions", tx.id)
            db.session.commit()
            flash(f"La transaction {tx.reference_transaction} a été modifiée avec succès.", "success")
            return redirect(url_for('transactions.view_transaction', tx_id=tx.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"[TRANSACTIONS] Échec modification tx_id={tx_id} par user_id={current_user.id}: {e}")
            logger.error(traceback.format_exc())
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
    tx = db.session.get(Transaction, tx_id)
    if tx is None:
        abort(404)
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
        log_activity(current_user.id, f"Encaissement paiement transaction {tx.reference_transaction}", "paiements", new_pay.id)
        db.session.commit()
        flash("Le paiement a été enregistré avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[TRANSACTIONS] Échec ajout paiement tx_id={tx_id} par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'ajout du paiement. Veuillez réessayer.", "danger")
        
    return redirect(url_for('transactions.view_transaction', tx_id=tx_id))

# --- Ajouter un contrat PDF ---
@transactions.route('/contrat/ajouter/<int:tx_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def add_contract(tx_id):
    tx = db.session.get(Transaction, tx_id)
    if tx is None:
        abort(404)
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
    except (ValueError, TypeError):
        flash("Erreur dans les formats de dates.", "danger")
        return redirect(url_for('transactions.view_transaction', tx_id=tx_id))

    if date_debut and date_fin and date_debut >= date_fin:
        flash("La date de début doit être antérieure à la date de fin.", "danger")
        return redirect(url_for('transactions.view_transaction', tx_id=tx_id))

    if date_signature > date.today():
        flash("La date de signature ne peut pas être dans le futur.", "danger")
        return redirect(url_for('transactions.view_transaction', tx_id=tx_id))
        
    max_size = current_app.config.get('MAX_FILE_SIZE_PDF', 15 * 1024 * 1024)
    try:
        safe_path, rel_path, unique_name, file_size = validate_and_save_upload(
            file_storage=file,
            upload_subdir='documents',
            allowed_extensions=ALLOWED_PDFS,
            max_size=max_size,
            category='pdf',
            validate_magic=True,
            prefix='CONTRAT_',
            user_id=current_user.id
        )
    except UploadValidationError as e:
        flash(e.message, "danger")
        return redirect(url_for('transactions.view_transaction', tx_id=tx_id))
    
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
        log_activity(current_user.id, f"Ajout contrat {numero_contrat} pour transaction {tx.reference_transaction}", "contrats", new_contrat.id)
        db.session.commit()
        flash("Le contrat a été enregistré et téléversé.", "success")
    except Exception as e:
        db.session.rollback()
        if os.path.exists(safe_path):
            os.remove(safe_path)
        logger.error(f"[TRANSACTIONS] Échec ajout contrat tx_id={tx_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'enregistrement du contrat. Veuillez réessayer.", "danger")
        
    return redirect(url_for('transactions.view_transaction', tx_id=tx_id))

@transactions.route('/recu/<int:tx_id>', methods=['POST'])
@login_required
@role_required('Comptable', 'Agent immobilier')
def download_transaction_pdf(tx_id):
    try:
        tx = db.session.get(Transaction, tx_id)
        if tx is None:
            abort(404)
        pdf_buffer = generate_transaction_sheet_pdf(tx)
        log_activity(current_user.id, f"Génération PDF Fiche Transaction {tx.reference_transaction}", "transactions", tx.id)
        db.session.commit()
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"Fiche_Transaction_{tx.reference_transaction}.pdf"
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"[TRANSACTIONS] Échec génération PDF transaction tx_id={tx_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la génération du PDF. Veuillez réessayer.", "danger")
        return redirect(url_for('transactions.list_transactions'))

@transactions.route('/paiement/recu/<int:pay_id>', methods=['POST'])
@login_required
@role_required('Comptable', 'Agent immobilier')
def download_payment_receipt_pdf_route(pay_id):
    try:
        payment = db.session.get(Paiement, pay_id)
        if payment is None:
            abort(404)
        pdf_buffer = generate_payment_receipt_pdf(payment)
        log_activity(current_user.id, f"Génération PDF Reçu Paiement {payment.id}", "paiements", payment.id)
        db.session.commit()
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"Recu_Paiement_{payment.id}.pdf"
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"[TRANSACTIONS] Échec génération PDF reçu pay_id={pay_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la génération du reçu PDF. Veuillez réessayer.", "danger")
        return redirect(url_for('transactions.list_transactions'))
