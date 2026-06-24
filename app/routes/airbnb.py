from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, send_file
from flask_login import login_required, current_user
from app.models import BienAirbnb, ReservationAirbnb, Proprietaire, Utilisateur
from app.utils.helpers import log_activity
from app.services.pdf_service import generate_airbnb_sheet_pdf
from app import db
from datetime import datetime, date

airbnb = Blueprint('airbnb', __name__)

@airbnb.route('/')
@login_required
def list_biens():
    search = request.args.get('search', '')
    statut_filter = request.args.get('statut', '')
    ville_filter = request.args.get('ville', '')
    
    query = BienAirbnb.query
    
    if search:
        query = query.filter(
            (BienAirbnb.titre.ilike(f'%{search}%')) |
            (BienAirbnb.reference.ilike(f'%{search}%')) |
            (BienAirbnb.ville.ilike(f'%{search}%')) |
            (BienAirbnb.quartier.ilike(f'%{search}%'))
        )
    if statut_filter:
        query = query.filter(BienAirbnb.statut == statut_filter)
    if ville_filter:
        query = query.filter(BienAirbnb.ville.ilike(f'%{ville_filter}%'))
    
    biens = query.order_by(BienAirbnb.date_ajout.desc()).all()
    
    # Statistiques rapides
    total_biens = BienAirbnb.query.count()
    biens_actifs = BienAirbnb.query.filter_by(statut='Actif').count()
    reservations_mois = ReservationAirbnb.query.filter(
        ReservationAirbnb.statut.in_(['Confirmée', 'Terminée']),
        db.extract('month', ReservationAirbnb.date_arrivee) == date.today().month,
        db.extract('year', ReservationAirbnb.date_arrivee) == date.today().year
    ).count()
    
    return render_template('airbnb/list.html', 
                         biens=biens, search=search, 
                         statut=statut_filter, ville=ville_filter,
                         total_biens=total_biens, biens_actifs=biens_actifs,
                         reservations_mois=reservations_mois)

@airbnb.route('/ajouter', methods=['GET', 'POST'])
@login_required
def add_bien():
    if request.method == 'POST':
        # Génération de la référence unique
        count = BienAirbnb.query.count()
        reference = f"AIR-{datetime.utcnow().year}-{count + 1:04d}"
        
        new_bien = BienAirbnb(
            reference=reference,
            titre=request.form.get('titre'),
            description=request.form.get('description'),
            type_bien=request.form.get('type_bien'),
            adresse=request.form.get('adresse'),
            ville=request.form.get('ville'),
            quartier=request.form.get('quartier'),
            capacite=request.form.get('capacite') or 2,
            nombre_chambres=request.form.get('nombre_chambres') or None,
            nombre_lits=request.form.get('nombre_lits') or None,
            nombre_salles_bain=request.form.get('nombre_salles_bain') or None,
            prix_par_nuit=request.form.get('prix_par_nuit'),
            devise=request.form.get('devise') or 'EUR',
            frais_menage=request.form.get('frais_menage') or 0,
            proprietaire_id=request.form.get('proprietaire_id') or None,
            agent_id=request.form.get('agent_id') or None,
            lien_airbnb=request.form.get('lien_airbnb'),
            wifi='wifi' in request.form,
            parking='parking' in request.form,
            climatisation='climatisation' in request.form,
            piscine='piscine' in request.form,
            observations=request.form.get('observations')
        )
        
        try:
            db.session.add(new_bien)
            db.session.commit()
            log_activity(current_user.id, f"Création bien AirBNB: {new_bien.titre}", "biens_airbnb", new_bien.id)
            flash(f"Le bien AirBNB « {new_bien.titre} » a été créé (Réf: {reference}).", "success")
            return redirect(url_for('airbnb.view_bien', bien_id=new_bien.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Erreur lors de la création: {e}", "danger")
    
    proprietaires = Proprietaire.query.order_by(Proprietaire.nom.asc()).all()
    agents = Utilisateur.query.filter_by(role='Agent immobilier', actif=True).order_by(Utilisateur.nom.asc()).all()
    return render_template('airbnb/form.html', bien=None, proprietaires=proprietaires, agents=agents, action_title="Ajouter un bien AirBNB")

@airbnb.route('/modifier/<int:bien_id>', methods=['GET', 'POST'])
@login_required
def edit_bien(bien_id):
    bien = BienAirbnb.query.get_or_404(bien_id)
    
    if request.method == 'POST':
        bien.titre = request.form.get('titre')
        bien.description = request.form.get('description')
        bien.type_bien = request.form.get('type_bien')
        bien.adresse = request.form.get('adresse')
        bien.ville = request.form.get('ville')
        bien.quartier = request.form.get('quartier')
        bien.capacite = request.form.get('capacite') or 2
        bien.nombre_chambres = request.form.get('nombre_chambres') or None
        bien.nombre_lits = request.form.get('nombre_lits') or None
        bien.nombre_salles_bain = request.form.get('nombre_salles_bain') or None
        bien.prix_par_nuit = request.form.get('prix_par_nuit')
        bien.devise = request.form.get('devise') or 'EUR'
        bien.frais_menage = request.form.get('frais_menage') or 0
        bien.proprietaire_id = request.form.get('proprietaire_id') or None
        bien.agent_id = request.form.get('agent_id') or None
        bien.statut = request.form.get('statut')
        bien.lien_airbnb = request.form.get('lien_airbnb')
        bien.wifi = 'wifi' in request.form
        bien.parking = 'parking' in request.form
        bien.climatisation = 'climatisation' in request.form
        bien.piscine = 'piscine' in request.form
        bien.observations = request.form.get('observations')
        
        try:
            db.session.commit()
            log_activity(current_user.id, f"Modification bien AirBNB: {bien.titre}", "biens_airbnb", bien.id)
            flash(f"Le bien « {bien.titre} » a été mis à jour.", "success")
            return redirect(url_for('airbnb.view_bien', bien_id=bien.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Erreur de modification: {e}", "danger")
    
    proprietaires = Proprietaire.query.order_by(Proprietaire.nom.asc()).all()
    agents = Utilisateur.query.filter_by(role='Agent immobilier', actif=True).order_by(Utilisateur.nom.asc()).all()
    return render_template('airbnb/form.html', bien=bien, proprietaires=proprietaires, agents=agents, action_title=f"Modifier {bien.titre}")

@airbnb.route('/details/<int:bien_id>')
@login_required
def view_bien(bien_id):
    bien = BienAirbnb.query.get_or_404(bien_id)
    
    # Statistiques du bien
    total_reservations = len(bien.reservations)
    reservations_confirmees = sum(1 for r in bien.reservations if r.statut in ['Confirmée', 'Terminée'])
    revenus_total = sum(float(r.montant_net or r.montant_total or 0) for r in bien.reservations if r.statut in ['Confirmée', 'Terminée'])
    nuits_total = sum(r.nombre_nuits or 0 for r in bien.reservations if r.statut in ['Confirmée', 'Terminée'])
    
    return render_template('airbnb/view.html', bien=bien,
                         total_reservations=total_reservations,
                         reservations_confirmees=reservations_confirmees,
                         revenus_total=revenus_total,
                         nuits_total=nuits_total)

@airbnb.route('/supprimer/<int:bien_id>', methods=['POST'])
@login_required
def delete_bien(bien_id):
    if current_user.role not in ['Administrateur', 'Directeur']:
        abort(403)
    
    bien = BienAirbnb.query.get_or_404(bien_id)
    titre = bien.titre
    
    try:
        db.session.delete(bien)
        db.session.commit()
        log_activity(current_user.id, f"Suppression bien AirBNB: {titre}", "biens_airbnb", bien_id)
        flash(f"Le bien « {titre} » a été supprimé.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Impossible de supprimer ce bien: {e}", "danger")
    
    return redirect(url_for('airbnb.list_biens'))

@airbnb.route('/reservation/ajouter/<int:bien_id>', methods=['POST'])
@login_required
def add_reservation(bien_id):
    bien = BienAirbnb.query.get_or_404(bien_id)
    
    date_arrivee = datetime.strptime(request.form.get('date_arrivee'), '%Y-%m-%d').date()
    date_depart = datetime.strptime(request.form.get('date_depart'), '%Y-%m-%d').date()
    nombre_nuits = (date_depart - date_arrivee).days
    
    montant_total = float(request.form.get('montant_total') or 0)
    commission_airbnb = float(request.form.get('commission_airbnb') or 0)
    montant_net = montant_total - commission_airbnb
    
    new_reservation = ReservationAirbnb(
        bien_airbnb_id=bien_id,
        nom_voyageur=request.form.get('nom_voyageur'),
        telephone_voyageur=request.form.get('telephone_voyageur'),
        email_voyageur=request.form.get('email_voyageur'),
        nombre_voyageurs=request.form.get('nombre_voyageurs') or 1,
        date_arrivee=date_arrivee,
        date_depart=date_depart,
        nombre_nuits=nombre_nuits,
        montant_total=montant_total,
        devise=request.form.get('devise') or bien.devise,
        commission_airbnb=commission_airbnb,
        montant_net=montant_net,
        statut=request.form.get('statut') or 'Confirmée',
        observations=request.form.get('observations')
    )
    
    try:
        db.session.add(new_reservation)
        db.session.commit()
        log_activity(current_user.id, f"Nouvelle réservation AirBNB pour {bien.titre}: {new_reservation.nom_voyageur}", "reservations_airbnb", new_reservation.id)
        flash(f"Réservation de {new_reservation.nom_voyageur} enregistrée ({nombre_nuits} nuits).", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur d'enregistrement: {e}", "danger")
    
    return redirect(url_for('airbnb.view_bien', bien_id=bien_id))

@airbnb.route('/reservation/supprimer/<int:reservation_id>', methods=['POST'])
@login_required
def delete_reservation(reservation_id):
    reservation = ReservationAirbnb.query.get_or_404(reservation_id)
    bien_id = reservation.bien_airbnb_id
    
    try:
        db.session.delete(reservation)
        db.session.commit()
        log_activity(current_user.id, "Suppression réservation AirBNB", "reservations_airbnb", reservation_id)
        flash("Réservation supprimée.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur: {e}", "danger")
    
    return redirect(url_for('airbnb.view_bien', bien_id=bien_id))

@airbnb.route('/telecharger-pdf/<int:bien_id>')
@login_required
def download_airbnb_pdf(bien_id):
    bien = BienAirbnb.query.get_or_404(bien_id)
    pdf_buffer = generate_airbnb_sheet_pdf(bien)
    log_activity(current_user.id, f"Génération PDF Fiche AirBNB {bien.reference}", "biens_airbnb", bien.id)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Fiche_AirBNB_{bien.reference}.pdf"
    )
