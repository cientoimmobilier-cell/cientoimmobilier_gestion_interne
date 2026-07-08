from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models import CompteBancaire, Caisse, MouvementFinancier, Facture, Recu, Budget, Utilisateur, Client, Transaction
from datetime import datetime, timezone
from app.utils.helpers import log_activity, role_required
import re

finance = Blueprint('finance', __name__)

TYPES_MOUVEMENT_VALIDES = {'Recette', 'Dépense'}

def sanitize_text(value, max_length=500):
    """Nettoie et valide un champ texte pour éviter l'injection de HTML ou de données corrompues."""
    if not value:
        return None
    value = str(value).strip()
    # Rejeter tout contenu ressemblant à du HTML (> 200 chars avec balises)
    if len(value) > 200 and re.search(r'<[a-zA-Z]', value):
        return None
    # Tronquer si trop long
    return value[:max_length]

@finance.route('/')
@login_required
@role_required('Comptable', 'Agent immobilier')
def index():
    # Affichage du tableau de bord financier
    comptes = CompteBancaire.query.filter_by(actif=True).all()
    caisses = Caisse.query.filter_by(actif=True).all()
    
    # Calcul des soldes totaux
    total_banque = sum(compte.solde for compte in comptes) if comptes else 0
    total_caisse = sum(caisse.solde for caisse in caisses) if caisses else 0
    
    # Calculs journaliers et mensuels
    today = datetime.now(timezone.utc).date()
    current_month = today.month
    current_year = today.year
    
    mouvements_today = MouvementFinancier.query.filter(db.func.date(MouvementFinancier.date_mouvement) == today).all()
    mouvements_month = MouvementFinancier.query.filter(db.extract('month', MouvementFinancier.date_mouvement) == current_month, db.extract('year', MouvementFinancier.date_mouvement) == current_year).all()
    
    recettes_jour = sum(m.montant for m in mouvements_today if m.type_mouvement == 'Recette')
    depenses_jour = sum(m.montant for m in mouvements_today if m.type_mouvement == 'Dépense')
    
    recettes_mois = sum(m.montant for m in mouvements_month if m.type_mouvement == 'Recette')
    depenses_mois = sum(m.montant for m in mouvements_month if m.type_mouvement == 'Dépense')
    
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
    mouvements = MouvementFinancier.query.filter_by(type_mouvement='Recette').order_by(MouvementFinancier.date_mouvement.desc()).all()
    caisses = Caisse.query.filter_by(actif=True).all()
    comptes = CompteBancaire.query.filter_by(actif=True).all()
    return render_template('finance/mouvements.html', type_mvt='Recette', mouvements=mouvements, caisses=caisses, comptes=comptes)

@finance.route('/depenses')
@login_required
@role_required('Comptable', 'Agent immobilier')
def depenses():
    mouvements = MouvementFinancier.query.filter_by(type_mouvement='Dépense').order_by(MouvementFinancier.date_mouvement.desc()).all()
    caisses = Caisse.query.filter_by(actif=True).all()
    comptes = CompteBancaire.query.filter_by(actif=True).all()
    return render_template('finance/mouvements.html', type_mvt='Dépense', mouvements=mouvements, caisses=caisses, comptes=comptes)

@finance.route('/caisse')
@login_required
@role_required('Comptable', 'Agent immobilier')
def caisse():
    caisses = Caisse.query.filter_by(actif=True).all()
    mouvements = MouvementFinancier.query.filter(MouvementFinancier.caisse_id.isnot(None)).order_by(MouvementFinancier.date_mouvement.desc()).limit(50).all()
    return render_template('finance/caisse.html', caisses=caisses, mouvements=mouvements)

@finance.route('/banque')
@login_required
@role_required('Comptable', 'Agent immobilier')
def banque():
    comptes = CompteBancaire.query.filter_by(actif=True).all()
    mouvements = MouvementFinancier.query.filter(MouvementFinancier.compte_bancaire_id.isnot(None)).order_by(MouvementFinancier.date_mouvement.desc()).limit(50).all()
    return render_template('finance/banque.html', comptes=comptes, mouvements=mouvements)

@finance.route('/factures')
@login_required
@role_required('Comptable', 'Agent immobilier')
def factures():
    factures = Facture.query.order_by(Facture.date_emission.desc()).all()
    clients = Client.query.order_by(Client.nom.asc()).all()
    return render_template('finance/factures.html', factures=factures, clients=clients)

@finance.route('/recus')
@login_required
@role_required('Comptable', 'Agent immobilier')
def recus():
    recus = Recu.query.order_by(Recu.date_emission.desc()).all()
    clients = Client.query.order_by(Client.nom.asc()).all()
    return render_template('finance/recus.html', recus=recus, clients=clients)

@finance.route('/budgets')
@login_required
@role_required('Comptable', 'Agent immobilier')
def budgets():
    budgets = Budget.query.order_by(Budget.annee.desc(), Budget.mois.desc()).all()
    return render_template('finance/budgets.html', budgets=budgets)

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
        flash(f"Montant invalide : {e}", "danger")
        return redirect(request.referrer or url_for('finance.index'))
    
    devise = request.form.get('devise', 'EUR').strip()
    date_mvt_str = request.form.get('date_mouvement', '').strip()
    categorie = sanitize_text(request.form.get('categorie'), max_length=100)
    description = sanitize_text(request.form.get('description'), max_length=500)
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
                    
        db.session.commit()
        log_activity(current_user.id, f"Ajout {type_mouvement.lower()} : {montant} {devise}", "finance")
        flash(f"{type_mouvement} enregistrée avec succès et soldes mis à jour.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de l'enregistrement. Veuillez réessayer.", "danger")
        
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
        db.session.commit()
        flash("Caisse créée avec succès.", "success")
    except Exception as e:
        db.session.rollback()
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
        db.session.commit()
        flash("Compte bancaire ajouté avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de l'ajout du compte. Veuillez réessayer.", "danger")
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
        db.session.commit()
        flash("Facture émise avec succès.", "success")
    except Exception as e:
        db.session.rollback()
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
        db.session.commit()
        flash("Reçu généré avec succès.", "success")
    except Exception as e:
        db.session.rollback()
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
        db.session.commit()
        log_activity(current_user.id, f"Ajout budget : {categorie} {annee}", "finance")
        flash("Budget créé avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de la création du budget. Veuillez réessayer.", "danger")
    return redirect(url_for('finance.budgets'))

