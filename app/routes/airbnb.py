import logging
import traceback
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, send_file
from flask_login import login_required, current_user
from app.models import BienAirbnb, ReservationAirbnb, Proprietaire, Utilisateur
from app.utils.helpers import log_activity, sanitize_search, role_required
from app.services.pdf_service import generate_airbnb_sheet_pdf
from sqlalchemy.orm import joinedload
from sqlalchemy import select, func as sa_func
from app import db
from datetime import datetime, date, timezone

logger = logging.getLogger(__name__)

airbnb = Blueprint('airbnb', __name__)

@airbnb.route('/')
@login_required
def list_biens():
    search = request.args.get('search', '')
    statut_filter = request.args.get('statut', '')
    ville_filter = request.args.get('ville', '')
    sort = request.args.get('sort', 'date_ajout')
    order = request.args.get('order', 'desc')
    per_page = request.args.get('per_page', 20, type=int)

    stmt = select(BienAirbnb).options(joinedload(BienAirbnb.proprietaire_airbnb))

    if search:
        safe_search = sanitize_search(search)
        like_pattern = f'%{safe_search}%'
        stmt = stmt.where(
            (BienAirbnb.titre.ilike(like_pattern)) |
            (BienAirbnb.reference.ilike(like_pattern)) |
            (BienAirbnb.ville.ilike(like_pattern)) |
            (BienAirbnb.quartier.ilike(like_pattern))
        )
    if statut_filter:
        stmt = stmt.where(BienAirbnb.statut == statut_filter)
    if ville_filter:
        stmt = stmt.where(BienAirbnb.ville.ilike(f'%{sanitize_search(ville_filter)}%'))

    page = request.args.get('page', 1, type=int)
    sort_column = getattr(BienAirbnb, sort, None)
    if sort_column is None:
        sort_column = BienAirbnb.date_ajout
        order = 'desc'
    stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    biens = pagination.items

    # Statistiques rapides
    total_biens = db.session.execute(select(sa_func.count(BienAirbnb.id))).scalar()
    biens_actifs = db.session.execute(select(sa_func.count(BienAirbnb.id)).where(BienAirbnb.statut == 'Actif')).scalar()
    reservations_mois = db.session.execute(select(sa_func.count(ReservationAirbnb.id)).where(
        ReservationAirbnb.statut.in_(['Confirmée', 'Terminée']),
        db.extract('month', ReservationAirbnb.date_arrivee) == date.today().month,
        db.extract('year', ReservationAirbnb.date_arrivee) == date.today().year
    )).scalar()

    return render_template('airbnb/list.html',
                         biens=biens, pagination=pagination, search=search,
                         statut=statut_filter, ville=ville_filter,
                         sort=sort, order=order, per_page=per_page,
                         total_biens=total_biens, biens_actifs=biens_actifs,
                         reservations_mois=reservations_mois)

@airbnb.route('/ajouter', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier', 'Assistant')
def add_bien():
    if request.method == 'POST':
        # Génération de la référence unique
        count = db.session.execute(select(sa_func.count(BienAirbnb.id))).scalar()
        reference = f"AIR-{datetime.now(timezone.utc).year}-{count + 1:04d}"
        
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
            log_activity(current_user.id, f"Création bien AirBNB: {new_bien.titre}", "biens_airbnb", new_bien.id)
            db.session.commit()
            flash(f"Le bien AirBNB « {new_bien.titre} » a été créé (Réf: {reference}).", "success")
            return redirect(url_for('airbnb.view_bien', bien_id=new_bien.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"[AIRBNB] Échec création bien par user_id={current_user.id}: {e}")
            logger.error(traceback.format_exc())
            flash("Erreur lors de la création du bien. Veuillez réessayer.", "danger")
    
    proprietaires = db.session.execute(select(Proprietaire).order_by(Proprietaire.nom.asc())).scalars().all()
    agents = db.session.execute(select(Utilisateur).where(Utilisateur.role == 'Agent immobilier', Utilisateur.actif == True).order_by(Utilisateur.nom.asc())).scalars().all()
    return render_template('airbnb/form.html', bien=None, proprietaires=proprietaires, agents=agents, action_title="Ajouter un bien AirBNB")

@airbnb.route('/modifier/<int:bien_id>', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier', 'Assistant')
def edit_bien(bien_id):
    bien = db.session.get(BienAirbnb, bien_id)
    if bien is None:
        abort(404)
    
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
            log_activity(current_user.id, f"Modification bien AirBNB: {bien.titre}", "biens_airbnb", bien.id)
            db.session.commit()
            flash(f"Le bien « {bien.titre} » a été mis à jour.", "success")
            return redirect(url_for('airbnb.view_bien', bien_id=bien.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"[AIRBNB] Échec modification bien id={bien_id} par user_id={current_user.id}: {e}")
            logger.error(traceback.format_exc())
            flash("Erreur lors de la modification. Veuillez réessayer.", "danger")
    
    proprietaires = db.session.execute(select(Proprietaire).order_by(Proprietaire.nom.asc())).scalars().all()
    agents = db.session.execute(select(Utilisateur).where(Utilisateur.role == 'Agent immobilier', Utilisateur.actif == True).order_by(Utilisateur.nom.asc())).scalars().all()
    return render_template('airbnb/form.html', bien=bien, proprietaires=proprietaires, agents=agents, action_title=f"Modifier {bien.titre}")

@airbnb.route('/details/<int:bien_id>')
@login_required
def view_bien(bien_id):
    bien = db.session.get(BienAirbnb, bien_id)
    if bien is None:
        abort(404)
    
    # Statistiques du bien via SQL
    total_reservations = db.session.execute(select(sa_func.count(ReservationAirbnb.id)).where(ReservationAirbnb.bien_airbnb_id == bien_id)).scalar() or 0
    
    reservations_confirmees = db.session.execute(select(sa_func.count(ReservationAirbnb.id)).where(
        ReservationAirbnb.bien_airbnb_id == bien_id,
        ReservationAirbnb.statut.in_(['Confirmée', 'Terminée'])
    )).scalar() or 0
    
    revenus_total = db.session.execute(select(
        sa_func.sum(sa_func.coalesce(ReservationAirbnb.montant_net, ReservationAirbnb.montant_total, 0))
    ).where(
        ReservationAirbnb.bien_airbnb_id == bien_id,
        ReservationAirbnb.statut.in_(['Confirmée', 'Terminée'])
    )).scalar() or 0
    
    nuits_total = db.session.execute(select(
        sa_func.sum(sa_func.coalesce(ReservationAirbnb.nombre_nuits, 0))
    ).where(
        ReservationAirbnb.bien_airbnb_id == bien_id,
        ReservationAirbnb.statut.in_(['Confirmée', 'Terminée'])
    )).scalar() or 0
    
    return render_template('airbnb/view.html', bien=bien,
                         total_reservations=total_reservations,
                         reservations_confirmees=reservations_confirmees,
                         revenus_total=revenus_total,
                         nuits_total=nuits_total)

@airbnb.route('/supprimer/<int:bien_id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def delete_bien(bien_id):
    bien = db.session.get(BienAirbnb, bien_id)
    if bien is None:
        abort(404)
    titre = bien.titre
    
    try:
        db.session.delete(bien)
        log_activity(current_user.id, f"Suppression bien AirBNB: {titre}", "biens_airbnb", bien_id)
        db.session.commit()
        flash(f"Le bien « {titre} » a été supprimé.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[AIRBNB] Échec suppression bien id={bien_id} par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Impossible de supprimer ce bien. Veuillez réessayer.", "danger")
    
    return redirect(url_for('airbnb.list_biens'))

@airbnb.route('/reservation/ajouter/<int:bien_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier', 'Assistant')
def add_reservation(bien_id):
    bien = db.session.get(BienAirbnb, bien_id)
    if bien is None:
        abort(404)
    
    try:
        date_arrivee = datetime.strptime(request.form.get('date_arrivee', ''), '%Y-%m-%d').date()
        date_depart = datetime.strptime(request.form.get('date_depart', ''), '%Y-%m-%d').date()
    except ValueError:
        flash("Format de date invalide pour l'arrivée ou le départ.", "danger")
        return redirect(url_for('airbnb.view_bien', bien_id=bien_id))

    if date_depart <= date_arrivee:
        flash("La date de départ doit être postérieure à la date d'arrivée.", "danger")
        return redirect(url_for('airbnb.view_bien', bien_id=bien_id))

    if date_arrivee < date.today():
        flash("La date d'arrivée ne peut pas être dans le passé.", "danger")
        return redirect(url_for('airbnb.view_bien', bien_id=bien_id))

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
        log_activity(current_user.id, f"Nouvelle réservation AirBNB pour {bien.titre}: {new_reservation.nom_voyageur}", "reservations_airbnb", new_reservation.id)
        db.session.commit()
        flash(f"Réservation de {new_reservation.nom_voyageur} enregistrée ({nombre_nuits} nuits).", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[AIRBNB] Échec création réservation pour bien_id={bien_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'enregistrement de la réservation. Veuillez réessayer.", "danger")
    
    return redirect(url_for('airbnb.view_bien', bien_id=bien_id))

@airbnb.route('/reservation/supprimer/<int:reservation_id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def delete_reservation(reservation_id):
    reservation = db.session.get(ReservationAirbnb, reservation_id)
    if reservation is None:
        abort(404)
    bien_id = reservation.bien_airbnb_id
    
    try:
        db.session.delete(reservation)
        log_activity(current_user.id, "Suppression réservation AirBNB", "reservations_airbnb", reservation_id)
        db.session.commit()
        flash("Réservation supprimée.", "info")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[AIRBNB] Échec suppression réservation id={reservation_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la suppression de la réservation. Veuillez réessayer.", "danger")
    
    return redirect(url_for('airbnb.view_bien', bien_id=bien_id))

@airbnb.route('/telecharger-pdf/<int:bien_id>')
@login_required
def download_airbnb_pdf(bien_id):
    try:
        bien = db.session.get(BienAirbnb, bien_id)
        if bien is None:
            abort(404)
        pdf_buffer = generate_airbnb_sheet_pdf(bien)
        log_activity(current_user.id, f"Génération PDF Fiche AirBNB {bien.reference}", "biens_airbnb", bien.id)
        db.session.commit()
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"Fiche_AirBNB_{bien.reference}.pdf"
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"[AIRBNB] Échec génération PDF bien_id={bien_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la génération du PDF. Veuillez réessayer.", "danger")
        return redirect(url_for('airbnb.list_biens'))
