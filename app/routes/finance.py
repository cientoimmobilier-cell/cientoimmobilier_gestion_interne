import logging
import traceback
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models import CompteBancaire, Caisse, MouvementFinancier, Facture, Recu, Budget, Client
from datetime import datetime, timezone, date
from sqlalchemy.orm import joinedload
from sqlalchemy import select, func as sa_func
from app.utils.helpers import log_activity, role_required, sanitize_input, sanitize_search

logger = logging.getLogger(__name__)

finance = Blueprint('finance', __name__)

TYPES_MOUVEMENT_VALIDES = {'Recette', 'Dépense'}

@finance.route('/')
@login_required
@role_required('Comptable', 'Agent immobilier')
def index():
    # Affichage du tableau de bord financier
    comptes = db.session.execute(select(CompteBancaire).where(CompteBancaire.actif == True)).scalars().all()
    caisses = db.session.execute(select(Caisse).where(Caisse.actif == True)).scalars().all()
    
    # Calcul des soldes totaux via DB
    total_banque = db.session.execute(select(sa_func.sum(CompteBancaire.solde)).where(CompteBancaire.actif == True)).scalar() or 0
    total_caisse = db.session.execute(select(sa_func.sum(Caisse.solde)).where(Caisse.actif == True)).scalar() or 0
    
    # Calculs journaliers et mensuels via agrégations SQL
    today = datetime.now(timezone.utc).date()
    current_month = today.month
    current_year = today.year
    
    recettes_jour = db.session.execute(select(sa_func.sum(MouvementFinancier.montant)).where(
        db.func.date(MouvementFinancier.date_mouvement) == today,
        MouvementFinancier.type_mouvement == 'Recette'
    )).scalar() or 0
    
    depenses_jour = db.session.execute(select(sa_func.sum(MouvementFinancier.montant)).where(
        db.func.date(MouvementFinancier.date_mouvement) == today,
        MouvementFinancier.type_mouvement == 'Dépense'
    )).scalar() or 0
    
    recettes_mois = db.session.execute(select(sa_func.sum(MouvementFinancier.montant)).where(
        db.extract('month', MouvementFinancier.date_mouvement) == current_month,
        db.extract('year', MouvementFinancier.date_mouvement) == current_year,
        MouvementFinancier.type_mouvement == 'Recette'
    )).scalar() or 0
    
    depenses_mois = db.session.execute(select(sa_func.sum(MouvementFinancier.montant)).where(
        db.extract('month', MouvementFinancier.date_mouvement) == current_month,
        db.extract('year', MouvementFinancier.date_mouvement) == current_year,
        MouvementFinancier.type_mouvement == 'Dépense'
    )).scalar() or 0
    
    return render_template('finance/index.html', 
                           comptes=comptes, 
                           caisses=caisses,
                           total_banque=total_banque,
                           total_caisse=total_caisse,
                           recettes_jour=recettes_jour,
                           depenses_jour=depenses_jour,
                           recettes_mois=recettes_mois,
                           depenses_mois=depenses_mois)

@finance.route('/recettes')
@login_required
@role_required('Comptable', 'Agent immobilier')
def recettes():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'date_mouvement')
    order = request.args.get('order', 'desc')
    
    stmt = select(MouvementFinancier).options(
        joinedload(MouvementFinancier.caisse),
        joinedload(MouvementFinancier.compte_bancaire)
    ).where(MouvementFinancier.type_mouvement == 'Recette')
    
    if search:
        safe_search = sanitize_search(search)
        search_term = f'%{safe_search}%'
        stmt = stmt.where(
            db.or_(
                MouvementFinancier.description.ilike(search_term),
                MouvementFinancier.categorie.ilike(search_term)
            )
        )
    
    sort_column = getattr(MouvementFinancier, sort, MouvementFinancier.date_mouvement)
    try:
        stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    except:
        stmt = stmt.order_by(MouvementFinancier.date_mouvement.desc())
    
    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    mouvements = pagination.items
    
    caisses = db.session.execute(select(Caisse).where(Caisse.actif == True)).scalars().all()
    comptes = db.session.execute(select(CompteBancaire).where(CompteBancaire.actif == True)).scalars().all()
    return render_template('finance/mouvements.html', type_mvt='Recette', mouvements=mouvements, pagination=pagination, caisses=caisses, comptes=comptes, sort=sort, order=order)

@finance.route('/depenses')
@login_required
@role_required('Comptable', 'Agent immobilier')
def depenses():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'date_mouvement')
    order = request.args.get('order', 'desc')
    
    stmt = select(MouvementFinancier).options(
        joinedload(MouvementFinancier.caisse),
        joinedload(MouvementFinancier.compte_bancaire)
    ).where(MouvementFinancier.type_mouvement == 'Dépense')
    
    if search:
        safe_search = sanitize_search(search)
        search_term = f'%{safe_search}%'
        stmt = stmt.where(
            db.or_(
                MouvementFinancier.description.ilike(search_term),
                MouvementFinancier.categorie.ilike(search_term)
            )
        )
    
    sort_column = getattr(MouvementFinancier, sort, MouvementFinancier.date_mouvement)
    try:
        stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    except:
        stmt = stmt.order_by(MouvementFinancier.date_mouvement.desc())
    
    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    mouvements = pagination.items
    
    caisses = db.session.execute(select(Caisse).where(Caisse.actif == True)).scalars().all()
    comptes = db.session.execute(select(CompteBancaire).where(CompteBancaire.actif == True)).scalars().all()
    return render_template('finance/mouvements.html', type_mvt='Dépense', mouvements=mouvements, pagination=pagination, caisses=caisses, comptes=comptes, sort=sort, order=order)

@finance.route('/caisse')
@login_required
@role_required('Comptable', 'Agent immobilier')
def caisse():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'date_mouvement')
    order = request.args.get('order', 'desc')
    
    caisses = db.session.execute(select(Caisse).where(Caisse.actif == True)).scalars().all()
    stmt = select(MouvementFinancier).options(joinedload(MouvementFinancier.caisse)).where(MouvementFinancier.caisse_id.isnot(None))
    
    if search:
        safe_search = sanitize_search(search)
        search_term = f'%{safe_search}%'
        stmt = stmt.where(
            db.or_(
                MouvementFinancier.description.ilike(search_term),
                MouvementFinancier.categorie.ilike(search_term)
            )
        )
    
    sort_column = getattr(MouvementFinancier, sort, MouvementFinancier.date_mouvement)
    try:
        stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    except:
        stmt = stmt.order_by(MouvementFinancier.date_mouvement.desc())
    
    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    mouvements = pagination.items
    return render_template('finance/caisse.html', caisses=caisses, mouvements=mouvements, pagination=pagination, sort=sort, order=order)

@finance.route('/banque')
@login_required
@role_required('Comptable', 'Agent immobilier')
def banque():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'date_mouvement')
    order = request.args.get('order', 'desc')
    
    comptes = db.session.execute(select(CompteBancaire).where(CompteBancaire.actif == True)).scalars().all()
    stmt = select(MouvementFinancier).options(joinedload(MouvementFinancier.compte_bancaire)).where(MouvementFinancier.compte_bancaire_id.isnot(None))
    
    if search:
        safe_search = sanitize_search(search)
        search_term = f'%{safe_search}%'
        stmt = stmt.where(
            db.or_(
                MouvementFinancier.description.ilike(search_term),
                MouvementFinancier.categorie.ilike(search_term)
            )
        )
    
    sort_column = getattr(MouvementFinancier, sort, MouvementFinancier.date_mouvement)
    try:
        stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    except:
        stmt = stmt.order_by(MouvementFinancier.date_mouvement.desc())
    
    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    mouvements = pagination.items
    return render_template('finance/banque.html', comptes=comptes, mouvements=mouvements, pagination=pagination, sort=sort, order=order)

@finance.route('/factures')
@login_required
@role_required('Comptable', 'Agent immobilier')
def factures():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'date_emission')
    order = request.args.get('order', 'desc')
    
    stmt = select(Facture).options(joinedload(Facture.client_facture))
    
    if search:
        safe_search = sanitize_search(search)
        search_term = f'%{safe_search}%'
        stmt = stmt.where(Facture.numero_facture.ilike(search_term))
    
    sort_column = getattr(Facture, sort, Facture.date_emission)
    try:
        stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    except:
        stmt = stmt.order_by(Facture.date_emission.desc())
    
    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    factures_list = pagination.items
    clients = db.session.execute(select(Client).order_by(Client.nom.asc())).scalars().all()
    return render_template('finance/factures.html', factures=factures_list, pagination=pagination, clients=clients, sort=sort, order=order)

@finance.route('/recus')
@login_required
@role_required('Comptable', 'Agent immobilier')
def recus():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'date_emission')
    order = request.args.get('order', 'desc')
    
    stmt = select(Recu).options(joinedload(Recu.client_recu))
    
    if search:
        safe_search = sanitize_search(search)
        search_term = f'%{safe_search}%'
        stmt = stmt.where(Recu.numero_recu.ilike(search_term))
    
    sort_column = getattr(Recu, sort, Recu.date_emission)
    try:
        stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    except:
        stmt = stmt.order_by(Recu.date_emission.desc())
    
    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    recus_list = pagination.items
    clients = db.session.execute(select(Client).order_by(Client.nom.asc())).scalars().all()
    return render_template('finance/recus.html', recus=recus_list, pagination=pagination, clients=clients, sort=sort, order=order)

@finance.route('/budgets')
@login_required
@role_required('Comptable', 'Agent immobilier')
def budgets():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'annee')
    order = request.args.get('order', 'desc')
    
    stmt = select(Budget)
    
    if search:
        safe_search = sanitize_search(search)
        search_term = f'%{safe_search}%'
        stmt = stmt.where(Budget.categorie.ilike(search_term))
    
    sort_column = getattr(Budget, sort, Budget.annee)
    try:
        stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    except:
        stmt = stmt.order_by(Budget.annee.desc(), Budget.mois.desc())
    
    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    budgets_list = pagination.items
    return render_template('finance/budgets.html', budgets=budgets_list, pagination=pagination, sort=sort, order=order)

@finance.route('/mouvement/ajouter', methods=['POST'])
@login_required
@role_required('Comptable')
def add_mouvement():
    type_mouvement = request.form.get('type_mouvement', '').strip()
    
    # Validation du type de mouvement
    if type_mouvement not in TYPES_MOUVEMENT_VALIDES:
        flash("Type de mouvement invalide.", "danger")
        return redirect(request.referrer or url_for('finance.index'))
    
    try:
        montant = float(request.form.get('montant', 0))
        if montant <= 0:
            raise ValueError("Le montant doit être positif.")
    except (ValueError, TypeError) as e:
        flash("Montant invalide. Veuillez vérifier la valeur saisie.", "danger")
        return redirect(request.referrer or url_for('finance.index'))
    
    devise = request.form.get('devise', 'EUR').strip()
    date_mvt_str = request.form.get('date_mouvement', '').strip()
    categorie = sanitize_input(request.form.get('categorie'), max_length=100)
    description = sanitize_input(request.form.get('description'), max_length=500)
    methode_paiement = request.form.get('methode_paiement', '').strip()
    compte_bancaire_id = request.form.get('compte_bancaire_id') or None
    caisse_id = request.form.get('caisse_id') or None
    
    try:
        date_mvt = datetime.strptime(date_mvt_str, "%Y-%m-%d").date()
    except Exception:
        date_mvt = datetime.now(timezone.utc).date()
        
    mvt = MouvementFinancier(
        type_mouvement=type_mouvement,
        montant=montant,
        devise=devise,
        date_mouvement=date_mvt,
        categorie=categorie,
        description=description,
        methode_paiement=methode_paiement,
        compte_bancaire_id=compte_bancaire_id,
        caisse_id=caisse_id,
        utilisateur_id=current_user.id
    )
    
    try:
        db.session.add(mvt)
        
        # Mettre à jour le solde
        if compte_bancaire_id:
            compte = db.session.get(CompteBancaire, int(compte_bancaire_id))
            if compte:
                if type_mouvement == 'Recette':
                    compte.solde += montant
                elif type_mouvement == 'Dépense':
                    compte.solde -= montant
        elif caisse_id:
            caisse = db.session.get(Caisse, int(caisse_id))
            if caisse:
                if type_mouvement == 'Recette':
                    caisse.solde += montant
                elif type_mouvement == 'Dépense':
                    caisse.solde -= montant
                    
        log_activity(current_user.id, f"Ajout {type_mouvement.lower()} : {montant} {devise}", "finance")
        db.session.commit()
        flash(f"{type_mouvement} enregistrée avec succès et soldes mis à jour.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[FINANCE] Échec ajout mouvement par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'enregistrement du mouvement. Veuillez réessayer.", "danger")
        
    # Rediriger vers la bonne page selon le type de mouvement
    if type_mouvement == 'Recette':
        return redirect(url_for('finance.recettes'))
    elif type_mouvement == 'Dépense':
        return redirect(url_for('finance.depenses'))
    return redirect(url_for('finance.index'))

@finance.route('/caisse/ajouter', methods=['POST'])
@login_required
@role_required('Comptable')
def add_caisse():
    nom = request.form.get('nom')
    solde = request.form.get('solde', 0)
    devise = request.form.get('devise', 'EUR')
    
    caisse = Caisse(nom=nom, solde=solde, devise=devise, responsable_id=current_user.id)
    try:
        db.session.add(caisse)
        db.session.flush()
        log_activity(current_user.id, f"Création caisse: {nom}", "caisses", caisse.id)
        db.session.commit()
        flash("Caisse créée avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[FINANCE] Échec création caisse par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la création de la caisse. Veuillez réessayer.", "danger")
    return redirect(url_for('finance.caisse'))

@finance.route('/banque/ajouter', methods=['POST'])
@login_required
@role_required('Comptable')
def add_banque():
    nom_banque = request.form.get('nom_banque')
    numero_compte = request.form.get('numero_compte')
    titulaire = request.form.get('titulaire')
    solde = request.form.get('solde', 0)
    devise = request.form.get('devise', 'EUR')
    
    compte = CompteBancaire(nom_banque=nom_banque, numero_compte=numero_compte, titulaire=titulaire, solde=solde, devise=devise)
    try:
        db.session.add(compte)
        db.session.flush()
        log_activity(current_user.id, f"Ajout compte bancaire: {nom_banque} - {numero_compte}", "comptes_bancaires", compte.id)
        db.session.commit()
        flash("Compte bancaire ajouté avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[FINANCE] Échec ajout compte bancaire par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'ajout du compte bancaire. Veuillez réessayer.", "danger")
    return redirect(url_for('finance.banque'))

@finance.route('/facture/ajouter', methods=['POST'])
@login_required
@role_required('Comptable')
def add_facture():
    numero = request.form.get('numero_facture')
    client_id = request.form.get('client_id')
    montant_ht = float(request.form.get('montant_ht', 0))
    tva = float(request.form.get('tva_pourcentage', 0))
    montant_tva = montant_ht * (tva / 100)
    montant_ttc = montant_ht + montant_tva
    
    facture = Facture(
        numero_facture=numero,
        client_id=client_id,
        montant_ht=montant_ht,
        tva_pourcentage=tva,
        montant_tva=montant_tva,
        montant_ttc=montant_ttc,
        statut='Émise'
    )
    try:
        db.session.add(facture)
        db.session.flush()
        log_activity(current_user.id, f"Émission facture: {numero}", "factures", facture.id)
        db.session.commit()
        flash("Facture émise avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[FINANCE] Échec émission facture par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'émission de la facture. Veuillez réessayer.", "danger")
    return redirect(url_for('finance.factures'))

@finance.route('/recu/ajouter', methods=['POST'])
@login_required
@role_required('Comptable')
def add_recu():
    numero = request.form.get('numero_recu')
    client_id = request.form.get('client_id')
    montant = request.form.get('montant', 0)
    methode = request.form.get('methode_paiement')
    
    recu = Recu(
        numero_recu=numero,
        client_id=client_id,
        montant=montant,
        methode_paiement=methode
    )
    try:
        db.session.add(recu)
        db.session.flush()
        log_activity(current_user.id, f"Génération reçu: {numero}", "recus", recu.id)
        db.session.commit()
        flash("Reçu généré avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[FINANCE] Échec génération reçu par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la génération du reçu. Veuillez réessayer.", "danger")
    return redirect(url_for('finance.recus'))

@finance.route('/budget/ajouter', methods=['POST'])
@login_required
@role_required('Comptable')
def add_budget():
    annee = request.form.get('annee')
    mois = request.form.get('mois')
    categorie = request.form.get('categorie')
    montant_prevu = request.form.get('montant_prevu', 0)
    devise = request.form.get('devise', 'EUR')
    description = request.form.get('description')
    
    budget = Budget(
        annee=int(annee),
        mois=int(mois) if mois else None,
        categorie=categorie,
        montant_prevu=float(montant_prevu),
        devise=devise,
        description=description
    )
    try:
        db.session.add(budget)
        log_activity(current_user.id, f"Ajout budget : {categorie} {annee}", "budgets")
        db.session.commit()
        flash("Budget créé avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[FINANCE] Échec création budget par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la création du budget. Veuillez réessayer.", "danger")
    return redirect(url_for('finance.budgets'))

