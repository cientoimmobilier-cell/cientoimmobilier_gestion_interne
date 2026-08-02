import logging
import traceback
from io import BytesIO
from datetime import datetime, timezone, date

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, current_app, send_file, jsonify
from flask_login import login_required, current_user
from sqlalchemy import select, func as sa_func

from app import db
from app.models import (
    Occupation, Occupant, RapportVisite, DocumentOccupation,
    Client, Propriete, Contrat, Utilisateur, Proprietaire, Transaction
)
from app.utils.helpers import log_activity, role_required, sanitize_search, safe_path_join
from app.utils.upload_security import (
    validate_and_save_upload, UploadValidationError,
    ALLOWED_DOCUMENTS, ALLOWED_IMAGES, ALLOWED_PDFS
)
from app.services.excel_service import export_occupations_to_excel
from app.services.pdf_service import generate_occupation_fiche_pdf
import os

logger = logging.getLogger(__name__)

occupation = Blueprint('occupation', __name__)


# ── Utilitaires ──────────────────────────────────────────────────────

def _generate_numero():
    count = db.session.execute(select(sa_func.count(Occupation.id))).scalar()
    return f"OCC-{datetime.now(timezone.utc).year}-{count + 1:04d}"


def _get_occupation_or_404(occ_id):
    occ = db.session.get(Occupation, occ_id)
    if occ is None:
        abort(404)
    return occ


def _update_propriete_statut(propriete_id, statut):
    prop = db.session.get(Propriete, propriete_id)
    if prop:
        prop.statut = statut


def _log(user_id, action, table='occupations', record_id=None):
    log_activity(user_id, action, table, record_id)


def _to_decimal(value):
    """Convertit une valeur de formulaire en float si possible, sinon None."""
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _serialize_contrat(c):
    """Sérialise un contrat pour l'import AJAX dans le formulaire d'occupation."""
    tx = c.transaction
    client = tx.client if tx else None
    propriete = tx.propriete if tx else None
    proprietaire = propriete.proprietaire if propriete else None
    return {
        'id': c.id,
        'numero': c.numero_contrat,
        'date_signature': c.date_signature.strftime('%d/%m/%Y') if c.date_signature else '',
        'date_debut': c.date_debut.strftime('%d/%m/%Y') if c.date_debut else '',
        'date_fin': c.date_fin.strftime('%d/%m/%Y') if c.date_fin else '',
        'montant_loyer': float(c.montant_loyer) if c.montant_loyer is not None else None,
        'depot_garantie': float(c.depot_garantie) if c.depot_garantie is not None else None,
        'statut': c.statut or '--',
        'mode_paiement': c.mode_paiement or '--',
        'frequence': c.frequence or '--',
        'locataire': (f"{client.prenom} {client.nom}").strip() if client else '',
        'proprietaire': (f"{proprietaire.prenom} {proprietaire.nom}").strip() if proprietaire else '',
        'lien_pdf': c.fichier_pdf or '',
    }


# ── Import de contrats (AJAX / JSON) ─────────────────────────────────

@occupation.route('/contrats/recherche')
@login_required
@role_required('Agent immobilier')
def search_contracts():
    """Recherche AJAX de contrats existants pour lier à une occupation."""
    q = sanitize_search(request.args.get('q', '').strip())
    exclude_id = request.args.get('exclude_id', type=int)
    try:
        stmt = select(Contrat).join(Transaction, Contrat.transaction_id == Transaction.id, isouter=True)
        if q:
            like = f'%{q}%'
            stmt = stmt.join(Client, Transaction.client_id == Client.id, isouter=True).where(
                db.or_(
                    Contrat.numero_contrat.ilike(like),
                    Client.nom.ilike(like),
                    Client.prenom.ilike(like),
                )
            )
        if exclude_id:
            stmt = stmt.where(Contrat.id != exclude_id)
        stmt = stmt.order_by(Contrat.id.desc()).limit(50)
        contrats = db.session.execute(stmt).scalars().all()
        return jsonify({'ok': True, 'contrats': [_serialize_contrat(c) for c in contrats]})
    except Exception as e:
        logger.error(f'[OCCUPATION] Échec recherche contrats: {e}')
        logger.error(traceback.format_exc())
        return jsonify({'ok': False, 'error': 'Erreur lors de la recherche de contrats.'}), 500


@occupation.route('/contrats/importer-pdf', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def import_contract_pdf():
    """Import AJAX d'un contrat PDF : crée un Contrat puis le lie à l'occupation."""
    numero = (request.form.get('numero_contrat') or '').strip()
    date_sig_str = request.form.get('date_signature')
    date_deb_str = request.form.get('date_debut') or None
    date_fin_str = request.form.get('date_fin') or None

    if not numero:
        return jsonify({'ok': False, 'error': 'Le numéro de contrat est obligatoire.'}), 400
    if not date_sig_str:
        return jsonify({'ok': False, 'error': 'La date de signature est obligatoire.'}), 400

    existing = db.session.execute(
        select(Contrat).where(Contrat.numero_contrat == numero)
    ).scalars().first()
    if existing:
        return jsonify({'ok': False, 'error': f'Le contrat "{numero}" existe déjà dans le système.'}), 400

    try:
        date_signature = datetime.strptime(date_sig_str, '%Y-%m-%d').date()
        date_debut = datetime.strptime(date_deb_str, '%Y-%m-%d').date() if date_deb_str else None
        date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date() if date_fin_str else None
    except (ValueError, TypeError):
        return jsonify({'ok': False, 'error': 'Format de date invalide.'}), 400

    if date_debut and date_fin and date_debut >= date_fin:
        return jsonify({'ok': False, 'error': 'La date de début doit être antérieure à la date de fin.'}), 400

    rel_path = None
    safe_path = None
    file = request.files.get('contrat_pdf')
    if file and file.filename:
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
            return jsonify({'ok': False, 'error': e.message}), 400

    contrat = Contrat(
        transaction_id=None,
        numero_contrat=numero,
        date_signature=date_signature,
        date_debut=date_debut,
        date_fin=date_fin,
        montant_loyer=_to_decimal(request.form.get('montant_loyer')),
        depot_garantie=_to_decimal(request.form.get('depot_garantie')),
        mode_paiement=request.form.get('mode_paiement') or None,
        frequence=request.form.get('frequence') or None,
        statut=request.form.get('statut') or 'Actif',
        fichier_pdf=rel_path,
    )

    try:
        db.session.add(contrat)
        db.session.flush()
        _log(current_user.id, f'Import contrat PDF: {numero} (occupation)', 'contrats', contrat.id)
        db.session.commit()
        return jsonify({'ok': True, 'contrat': _serialize_contrat(contrat)})
    except Exception as e:
        db.session.rollback()
        if safe_path and os.path.exists(safe_path):
            os.remove(safe_path)
        logger.error(f'[OCCUPATION] Échec import contrat: {e}')
        logger.error(traceback.format_exc())
        return jsonify({'ok': False, 'error': 'Erreur lors de l\'import du contrat.'}), 500


# ── Dashboard ─────────────────────────────────────────────────────────

@occupation.route('/dashboard')
@login_required
def dashboard():
    today = date.today()
    first_of_month = today.replace(day=1)

    actives = db.session.execute(
        select(sa_func.count(Occupation.id)).where(Occupation.statut == 'Active')
    ).scalar() or 0

    terminees = db.session.execute(
        select(sa_func.count(Occupation.id)).where(Occupation.statut == 'Terminée')
    ).scalar() or 0

    entrees_mois = db.session.execute(
        select(sa_func.count(Occupation.id)).where(
            Occupation.date_entree >= first_of_month,
            Occupation.date_entree <= today
        )
    ).scalar() or 0

    sorties_mois = db.session.execute(
        select(sa_func.count(Occupation.id)).where(
            Occupation.date_sortie_reelle >= first_of_month,
            Occupation.date_sortie_reelle <= today
        )
    ).scalar() or 0

    biens_occupes = db.session.execute(
        select(sa_func.count(Propriete.id)).where(Propriete.statut == 'Occupé')
    ).scalar() or 0

    biens_disponibles = db.session.execute(
        select(sa_func.count(Propriete.id)).where(Propriete.statut == 'Disponible')
    ).scalar() or 0

    total_biens_immo = biens_occupes + biens_disponibles
    taux = round((biens_occupes / total_biens_immo) * 100, 1) if total_biens_immo > 0 else 0

    total_occupants = db.session.execute(
        select(sa_func.count(Occupant.id))
    ).scalar() or 0

    visites_effectuees = db.session.execute(
        select(sa_func.count(RapportVisite.id))
    ).scalar() or 0

    # Dernières occupations actives
    dernieres = db.session.execute(
        select(Occupation).where(Occupation.statut == 'Active')
        .order_by(Occupation.date_modification.desc()).limit(5)
    ).scalars().all()

    return render_template('occupation/dashboard.html',
        actives=actives, terminees=terminees,
        entrees_mois=entrees_mois, sorties_mois=sorties_mois,
        biens_occupes=biens_occupes, biens_disponibles=biens_disponibles,
        taux=taux, total_occupants=total_occupants,
        visites_effectuees=visites_effectuees,
        dernieres=dernieres
    )


# ── Liste ──────────────────────────────────────────────────────────────

@occupation.route('/')
@login_required
def list_occupations():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'date_creation')
    order = request.args.get('order', 'desc')
    statut = request.args.get('statut', '')
    ville = request.args.get('ville', '')
    agent_id = request.args.get('agent_id', type=int)
    proprietaire_id = request.args.get('proprietaire_id', type=int)

    stmt = select(Occupation)

    if search:
        safe = sanitize_search(search)
        like = f'%{safe}%'
        stmt = stmt.join(Client, Occupation.client_id == Client.id, isouter=True).join(
            Propriete, Occupation.propriete_id == Propriete.id, isouter=True
        ).where(
            db.or_(
                Occupation.numero_occupation.ilike(like),
                Client.nom.ilike(like), Client.prenom.ilike(like),
                Client.code_client.ilike(like),
                Propriete.reference_bien.ilike(like),
                Propriete.adresse.ilike(like),
                Propriete.ville.ilike(like)
            )
        )

    if statut:
        stmt = stmt.where(Occupation.statut == statut)
    if ville:
        stmt = stmt.join(Propriete, Occupation.propriete_id == Propriete.id).where(Propriete.ville == ville)
    if agent_id:
        stmt = stmt.where(Occupation.agent_id == agent_id)
    if proprietaire_id:
        stmt = stmt.join(Propriete, Occupation.propriete_id == Propriete.id).where(Propriete.proprietaire_id == proprietaire_id)

    sort_col = getattr(Occupation, sort, Occupation.date_creation)
    try:
        stmt = stmt.order_by(sort_col.asc() if order == 'asc' else sort_col.desc())
    except Exception:
        stmt = stmt.order_by(Occupation.date_creation.desc())

    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    statuts = ['En préparation', 'Active', 'Terminée', 'Résiliée']
    villes = db.session.execute(
        select(Propriete.ville).where(Propriete.ville.isnot(None)).distinct().order_by(Propriete.ville.asc())
    ).scalars().all()
    agents_list = db.session.execute(
        select(Utilisateur).where(Utilisateur.actif == True).order_by(Utilisateur.nom.asc())
    ).scalars().all()
    proprietaires = db.session.execute(
        select(Proprietaire).order_by(Proprietaire.nom.asc())
    ).scalars().all()

    return render_template('occupation/list.html',
        pagination=pagination, search=search, sort=sort, order=order,
        statut=statut, ville=ville, agent_id=agent_id,
        proprietaire_id=proprietaire_id,
        statuts=statuts, villes=villes,
        agents_list=agents_list, proprietaires=proprietaires
    )


# ── Création ──────────────────────────────────────────────────────────

@occupation.route('/creer', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier')
def create_occupation():
    clients = db.session.execute(
        select(Client).order_by(Client.nom.asc())
    ).scalars().all()

    biens = db.session.execute(
        select(Propriete).where(Propriete.statut.in_(['Disponible', 'Réservé', 'Occupé']))
        .order_by(Propriete.titre.asc())
    ).scalars().all()

    contrats = db.session.execute(
        select(Contrat).order_by(Contrat.numero_contrat.asc())
    ).scalars().all()

    agents_list = db.session.execute(
        select(Utilisateur).where(Utilisateur.actif == True).order_by(Utilisateur.nom.asc())
    ).scalars().all()

    if request.method == 'POST':
        client_id = request.form.get('client_id', type=int)
        propriete_id = request.form.get('propriete_id', type=int)
        contrat_id = request.form.get('contrat_id', type=int)
        agent_id = request.form.get('agent_id', type=int)
        date_entree_str = request.form.get('date_entree')
        date_sortie_prevue_str = request.form.get('date_sortie_prevue')
        observations = request.form.get('observations')

        # Validations
        if not client_id:
            flash('Veuillez sélectionner un client.', 'danger')
            return render_template('occupation/form.html', occupation=None,
                clients=clients, biens=biens, contrats=contrats,
                agents_list=agents_list, action_title='Nouvelle occupation')

        if not propriete_id:
            flash('Veuillez sélectionner un bien.', 'danger')
            return render_template('occupation/form.html', occupation=None,
                clients=clients, biens=biens, contrats=contrats,
                agents_list=agents_list, action_title='Nouvelle occupation')

        if not contrat_id:
            flash("Un contrat de bail valide est obligatoire. Importez ou recherchez un contrat existant.", 'danger')
            return render_template('occupation/form.html', occupation=None,
                clients=clients, biens=biens, contrats=contrats,
                agents_list=agents_list, action_title='Nouvelle occupation')

        if not agent_id:
            flash('Veuillez sélectionner un agent responsable.', 'danger')
            return render_template('occupation/form.html', occupation=None,
                clients=clients, biens=biens, contrats=contrats,
                agents_list=agents_list, action_title='Nouvelle occupation')

        try:
            date_entree = datetime.strptime(date_entree_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            flash('Format de date d\'entrée invalide.', 'danger')
            return render_template('occupation/form.html', occupation=None,
                clients=clients, biens=biens, contrats=contrats,
                agents_list=agents_list, action_title='Nouvelle occupation')

        date_sortie_prevue = None
        if date_sortie_prevue_str:
            try:
                date_sortie_prevue = datetime.strptime(date_sortie_prevue_str, '%Y-%m-%d').date()
                if date_sortie_prevue <= date_entree:
                    flash('La date de sortie prévue doit être postérieure à la date d\'entrée.', 'danger')
                    return render_template('occupation/form.html', occupation=None,
                        clients=clients, biens=biens, contrats=contrats,
                        agents_list=agents_list, action_title='Nouvelle occupation')
            except (ValueError, TypeError):
                flash('Format de date de sortie prévue invalide.', 'danger')
                return render_template('occupation/form.html', occupation=None,
                    clients=clients, biens=biens, contrats=contrats,
                    agents_list=agents_list, action_title='Nouvelle occupation')

        # Vérifier qu'il n'y a pas déjà une occupation active sur ce bien
        active_occ = db.session.execute(
            select(Occupation).where(
                Occupation.propriete_id == propriete_id,
                Occupation.statut == 'Active'
            )
        ).scalars().first()

        if active_occ:
            flash(f'Ce bien a déjà une occupation active ({active_occ.numero_occupation}).', 'danger')
            return render_template('occupation/form.html', occupation=None,
                clients=clients, biens=biens, contrats=contrats,
                agents_list=agents_list, action_title='Nouvelle occupation')

        occ = Occupation(
            numero_occupation=_generate_numero(),
            statut='En préparation',
            client_id=client_id,
            propriete_id=propriete_id,
            contrat_id=contrat_id,
            agent_id=agent_id,
            date_entree=date_entree,
            date_sortie_prevue=date_sortie_prevue,
            observations=observations
        )

        try:
            db.session.add(occ)
            db.session.flush()
            _log(current_user.id, f'Création occupation: {occ.numero_occupation}', 'occupations', occ.id)
            db.session.commit()
            flash(f'Occupation {occ.numero_occupation} créée avec succès.', 'success')
            return redirect(url_for('occupation.view_occupation', occ_id=occ.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f'[OCCUPATION] Échec création: {e}')
            logger.error(traceback.format_exc())
            flash('Erreur lors de la création. Veuillez réessayer.', 'danger')

    return render_template('occupation/form.html', occupation=None,
        clients=clients, biens=biens, contrats=contrats,
        agents_list=agents_list, action_title='Nouvelle occupation')


# ── Détail ────────────────────────────────────────────────────────────

@occupation.route('/<int:occ_id>')
@login_required
def view_occupation(occ_id):
    occ = _get_occupation_or_404(occ_id)
    occupants = occ.occupants.order_by(Occupant.nom.asc()).all()
    rapports = occ.rapports.order_by(RapportVisite.date_visite.desc()).all()
    documents = occ.documents.order_by(DocumentOccupation.date_upload.desc()).all()
    agents_list = db.session.execute(
        select(Utilisateur).where(Utilisateur.actif == True).order_by(Utilisateur.nom.asc())
    ).scalars().all()
    return render_template('occupation/detail.html',
        occ=occ, occupants=occupants, rapports=rapports,
        documents=documents, agents_list=agents_list
    )


# ── Modification ──────────────────────────────────────────────────────

@occupation.route('/modifier/<int:occ_id>', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier')
def edit_occupation(occ_id):
    occ = _get_occupation_or_404(occ_id)

    clients = db.session.execute(select(Client).order_by(Client.nom.asc())).scalars().all()
    biens = db.session.execute(select(Propriete).order_by(Propriete.titre.asc())).scalars().all()
    contrats = db.session.execute(select(Contrat).order_by(Contrat.numero_contrat.asc())).scalars().all()
    agents_list = db.session.execute(
        select(Utilisateur).where(Utilisateur.actif == True).order_by(Utilisateur.nom.asc())
    ).scalars().all()

    if request.method == 'POST':
        occ.client_id = request.form.get('client_id', type=int)
        occ.propriete_id = request.form.get('propriete_id', type=int)
        occ.contrat_id = request.form.get('contrat_id', type=int)
        occ.agent_id = request.form.get('agent_id', type=int)

        if not occ.contrat_id:
            flash('Un contrat valide doit être associé à l\'occupation.', 'danger')
            return render_template('occupation/form.html', occupation=occ,
                clients=clients, biens=biens, contrats=contrats,
                agents_list=agents_list, action_title=f'Modifier {occ.numero_occupation}')

        date_entree_str = request.form.get('date_entree')
        date_sortie_prevue_str = request.form.get('date_sortie_prevue')
        date_sortie_reelle_str = request.form.get('date_sortie_reelle')
        occ.observations = request.form.get('observations')

        try:
            occ.date_entree = datetime.strptime(date_entree_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            flash('Format de date d\'entrée invalide.', 'danger')
            return render_template('occupation/form.html', occupation=occ,
                clients=clients, biens=biens, contrats=contrats,
                agents_list=agents_list, action_title=f'Modifier {occ.numero_occupation}')

        if date_sortie_prevue_str:
            try:
                occ.date_sortie_prevue = datetime.strptime(date_sortie_prevue_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                flash('Format de date de sortie prévue invalide.', 'danger')
                return render_template('occupation/form.html', occupation=occ,
                    clients=clients, biens=biens, contrats=contrats,
                    agents_list=agents_list, action_title=f'Modifier {occ.numero_occupation}')
        else:
            occ.date_sortie_prevue = None

        if date_sortie_reelle_str:
            try:
                occ.date_sortie_reelle = datetime.strptime(date_sortie_reelle_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                flash('Format de date de sortie réelle invalide.', 'danger')
                return render_template('occupation/form.html', occupation=occ,
                    clients=clients, biens=biens, contrats=contrats,
                    agents_list=agents_list, action_title=f'Modifier {occ.numero_occupation}')
        else:
            occ.date_sortie_reelle = None

        try:
            _log(current_user.id, f'Modification occupation: {occ.numero_occupation}', 'occupations', occ.id)
            db.session.commit()
            flash(f'Occupation {occ.numero_occupation} mise à jour.', 'success')
            return redirect(url_for('occupation.view_occupation', occ_id=occ.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f'[OCCUPATION] Échec modification occ_id={occ_id}: {e}')
            logger.error(traceback.format_exc())
            flash('Erreur lors de la modification. Veuillez réessayer.', 'danger')

    return render_template('occupation/form.html', occupation=occ,
        clients=clients, biens=biens, contrats=contrats,
        agents_list=agents_list, action_title=f'Modifier {occ.numero_occupation}')


# ── Changements de statut ─────────────────────────────────────────────

@occupation.route('/<int:occ_id>/activer', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def activate_occupation(occ_id):
    occ = _get_occupation_or_404(occ_id)
    if occ.statut != 'En préparation':
        flash('Seules les occupations en préparation peuvent être activées.', 'warning')
        return redirect(url_for('occupation.view_occupation', occ_id=occ_id))

    occ.statut = 'Active'
    occ.date_sortie_reelle = None
    _update_propriete_statut(occ.propriete_id, 'Occupé')

    try:
        _log(current_user.id, f'Activation occupation: {occ.numero_occupation}', 'occupations', occ.id)
        db.session.commit()
        flash(f'Occupation {occ.numero_occupation} activée. Le bien est maintenant marqué "Occupé".', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'[OCCUPATION] Échec activation occ_id={occ_id}: {e}')
        logger.error(traceback.format_exc())
        flash('Erreur lors de l\'activation.', 'danger')

    return redirect(url_for('occupation.view_occupation', occ_id=occ_id))


@occupation.route('/<int:occ_id>/terminer', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def terminate_occupation(occ_id):
    occ = _get_occupation_or_404(occ_id)
    if occ.statut != 'Active':
        flash('Seules les occupations actives peuvent être terminées.', 'warning')
        return redirect(url_for('occupation.view_occupation', occ_id=occ_id))

    date_sortie_str = request.form.get('date_sortie_reelle')
    if date_sortie_str:
        try:
            occ.date_sortie_reelle = datetime.strptime(date_sortie_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            flash('Format de date de sortie invalide.', 'danger')
            return redirect(url_for('occupation.view_occupation', occ_id=occ_id))
    else:
        occ.date_sortie_reelle = date.today()

    occ.statut = 'Terminée'
    _update_propriete_statut(occ.propriete_id, 'Disponible')

    try:
        _log(current_user.id, f'Fin occupation: {occ.numero_occupation}', 'occupations', occ.id)
        db.session.commit()
        flash(f'Occupation {occ.numero_occupation} terminée. Le bien est maintenant disponible.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'[OCCUPATION] Échec terminaison occ_id={occ_id}: {e}')
        logger.error(traceback.format_exc())
        flash('Erreur lors de la terminaison.', 'danger')

    return redirect(url_for('occupation.view_occupation', occ_id=occ_id))


@occupation.route('/<int:occ_id>/resilier', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def rescind_occupation(occ_id):
    occ = _get_occupation_or_404(occ_id)
    if occ.statut not in ('En préparation', 'Active'):
        flash('Cette occupation ne peut pas être résiliée.', 'warning')
        return redirect(url_for('occupation.view_occupation', occ_id=occ_id))

    was_active = occ.statut == 'Active'
    occ.statut = 'Résiliée'
    occ.date_sortie_reelle = date.today()
    if was_active:
        _update_propriete_statut(occ.propriete_id, 'Disponible')

    try:
        _log(current_user.id, f'Résiliation occupation: {occ.numero_occupation}', 'occupations', occ.id)
        db.session.commit()
        flash(f'Occupation {occ.numero_occupation} résiliée.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'[OCCUPATION] Échec résiliation occ_id={occ_id}: {e}')
        logger.error(traceback.format_exc())
        flash('Erreur lors de la résiliation.', 'danger')

    return redirect(url_for('occupation.view_occupation', occ_id=occ_id))


@occupation.route('/supprimer/<int:occ_id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def delete_occupation(occ_id):
    occ = _get_occupation_or_404(occ_id)

    # Supprimer les fichiers physiques
    static_dir = os.path.join(current_app.root_path, 'static')
    for doc in occ.documents:
        try:
            safe_path = safe_path_join(static_dir, doc.chemin_fichier)
            if safe_path and os.path.exists(safe_path):
                os.remove(safe_path)
        except Exception as e:
            logger.warning(f'Erreur suppression fichier doc_id={doc.id}: {e}')

    if occ.statut == 'Active':
        _update_propriete_statut(occ.propriete_id, 'Disponible')

    numero = occ.numero_occupation
    try:
        db.session.delete(occ)
        _log(current_user.id, f'Suppression occupation: {numero}', 'occupations', occ_id)
        db.session.commit()
        flash(f'Occupation {numero} supprimée.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'[OCCUPATION] Échec suppression occ_id={occ_id}: {e}')
        logger.error(traceback.format_exc())
        flash('Erreur lors de la suppression.', 'danger')

    return redirect(url_for('occupation.list_occupations'))


# ── Gestion des occupants ─────────────────────────────────────────────

@occupation.route('/<int:occ_id>/occupants/ajouter', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def add_occupant(occ_id):
    occ = _get_occupation_or_404(occ_id)

    occupant = Occupant(
        occupation_id=occ_id,
        nom=request.form.get('nom'),
        prenom=request.form.get('prenom'),
        sexe=request.form.get('sexe'),
        date_naissance=datetime.strptime(request.form['date_naissance'], '%Y-%m-%d').date()
            if request.form.get('date_naissance') else None,
        telephone=request.form.get('telephone'),
        numero_piece=request.form.get('numero_piece'),
        type_piece=request.form.get('type_piece'),
        lien_locataire=request.form.get('lien_locataire')
    )

    try:
        db.session.add(occupant)
        db.session.flush()
        _log(current_user.id, f'Ajout occupant {occupant.prenom} {occupant.nom} à {occ.numero_occupation}',
             'occupants', occupant.id)
        db.session.commit()
        flash(f'Occupant {occupant.prenom} {occupant.nom} ajouté.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'[OCCUPATION] Échec ajout occupant: {e}')
        logger.error(traceback.format_exc())
        flash('Erreur lors de l\'ajout de l\'occupant.', 'danger')

    return redirect(url_for('occupation.view_occupation', occ_id=occ_id))


@occupation.route('/<int:occ_id>/occupants/<int:occupant_id>/supprimer', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def delete_occupant(occ_id, occupant_id):
    occ = _get_occupation_or_404(occ_id)
    occupant = db.session.get(Occupant, occupant_id)
    if occupant is None or occupant.occupation_id != occ_id:
        abort(404)

    name = f'{occupant.prenom} {occupant.nom}'
    try:
        db.session.delete(occupant)
        _log(current_user.id, f'Suppression occupant {name} de {occ.numero_occupation}', 'occupants', occupant_id)
        db.session.commit()
        flash(f'Occupant {name} retiré.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'[OCCUPATION] Échec suppression occupant: {e}')
        logger.error(traceback.format_exc())
        flash('Erreur lors de la suppression de l\'occupant.', 'danger')

    return redirect(url_for('occupation.view_occupation', occ_id=occ_id))


# ── Rapports de visite ────────────────────────────────────────────────

@occupation.route('/<int:occ_id>/rapports/ajouter', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def add_rapport(occ_id):
    occ = _get_occupation_or_404(occ_id)

    date_str = request.form.get('date_visite')
    heure_str = request.form.get('heure_visite')

    try:
        if heure_str:
            date_visite = datetime.strptime(f'{date_str} {heure_str}', '%Y-%m-%d %H:%M')
        else:
            date_visite = datetime.strptime(date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        flash('Format de date ou heure invalide.', 'danger')
        return redirect(url_for('occupation.view_occupation', occ_id=occ_id))

    rapport = RapportVisite(
        occupation_id=occ_id,
        agent_id=request.form.get('agent_id', type=int) or current_user.id,
        date_visite=date_visite,
        type_visite=request.form.get('type_visite'),
        commentaires=request.form.get('commentaires'),
        observations=request.form.get('observations'),
        etat_general=request.form.get('etat_general'),
        travaux_prevoir=request.form.get('travaux_prevoir')
    )

    try:
        db.session.add(rapport)
        db.session.flush()
        _log(current_user.id, f'Ajout rapport {rapport.type_visite} à {occ.numero_occupation}',
             'rapports_visites', rapport.id)
        db.session.commit()
        flash('Rapport de visite ajouté.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'[OCCUPATION] Échec ajout rapport: {e}')
        logger.error(traceback.format_exc())
        flash('Erreur lors de l\'ajout du rapport.', 'danger')

    return redirect(url_for('occupation.view_occupation', occ_id=occ_id))


@occupation.route('/<int:occ_id>/rapports/<int:rapport_id>/supprimer', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def delete_rapport(occ_id, rapport_id):
    rapport = db.session.get(RapportVisite, rapport_id)
    if rapport is None or rapport.occupation_id != occ_id:
        abort(404)

    try:
        db.session.delete(rapport)
        _log(current_user.id, f'Suppression rapport visite id={rapport_id}', 'rapports_visites', rapport_id)
        db.session.commit()
        flash('Rapport supprimé.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'[OCCUPATION] Échec suppression rapport: {e}')
        logger.error(traceback.format_exc())
        flash('Erreur lors de la suppression du rapport.', 'danger')

    return redirect(url_for('occupation.view_occupation', occ_id=occ_id))


# ── Documents ─────────────────────────────────────────────────────────

@occupation.route('/<int:occ_id>/documents/upload', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def upload_document(occ_id):
    occ = _get_occupation_or_404(occ_id)

    if 'document' not in request.files:
        flash('Aucun fichier envoyé.', 'warning')
        return redirect(url_for('occupation.view_occupation', occ_id=occ_id))

    file = request.files['document']
    nom_document = request.form.get('nom_document') or file.filename
    max_size = current_app.config.get('MAX_FILE_SIZE_DOCUMENT', 15 * 1024 * 1024)

    try:
        safe_path, rel_path, unique_name, file_size = validate_and_save_upload(
            file_storage=file,
            upload_subdir='documents',
            allowed_extensions=ALLOWED_DOCUMENTS | ALLOWED_IMAGES,
            max_size=max_size,
            category='document',
            validate_magic=True,
            prefix=f'occ_{occ_id}_',
            user_id=current_user.id
        )
    except UploadValidationError as e:
        flash(e.message, 'danger')
        return redirect(url_for('occupation.view_occupation', occ_id=occ_id))

    doc_entry = DocumentOccupation(
        occupation_id=occ_id,
        nom_document=nom_document[:255],
        type_document=unique_name.rsplit('.', 1)[1].upper() if '.' in unique_name else 'UNKNOWN',
        chemin_fichier=rel_path
    )

    try:
        db.session.add(doc_entry)
        db.session.flush()
        _log(current_user.id, f'Ajout document {nom_document} à {occ.numero_occupation}',
             'documents_occupations', doc_entry.id)
        db.session.commit()
        flash(f'Document "{nom_document}" téléversé.', 'success')
    except Exception as e:
        db.session.rollback()
        if os.path.exists(safe_path):
            os.remove(safe_path)
        logger.error(f'[OCCUPATION] Échec enregistrement document: {e}')
        logger.error(traceback.format_exc())
        flash('Erreur lors de l\'enregistrement du document.', 'danger')

    return redirect(url_for('occupation.view_occupation', occ_id=occ_id))


@occupation.route('/<int:occ_id>/documents/<int:doc_id>/supprimer', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def delete_document(occ_id, doc_id):
    doc = db.session.get(DocumentOccupation, doc_id)
    if doc is None or doc.occupation_id != occ_id:
        abort(404)

    static_dir = os.path.join(current_app.root_path, 'static')
    safe_path = safe_path_join(static_dir, doc.chemin_fichier)
    try:
        if safe_path and os.path.exists(safe_path):
            os.remove(safe_path)
    except Exception as e:
        logger.warning(f'Erreur suppression fichier doc_id={doc_id}: {e}')

    try:
        db.session.delete(doc)
        _log(current_user.id, f'Suppression document {doc.nom_document}', 'documents_occupations', doc_id)
        db.session.commit()
        flash('Document supprimé.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'[OCCUPATION] Échec suppression document: {e}')
        logger.error(traceback.format_exc())
        flash('Erreur lors de la suppression du document.', 'danger')

    return redirect(url_for('occupation.view_occupation', occ_id=occ_id))


# ── Exports ───────────────────────────────────────────────────────────

@occupation.route('/exporter', methods=['POST'])
@login_required
def export_excel():
    try:
        occupations = db.session.execute(
            select(Occupation).order_by(Occupation.date_creation.desc())
        ).scalars().all()
        excel_file = export_occupations_to_excel(occupations)
        _log(current_user.id, 'Exportation Excel des occupations', 'occupations')
        db.session.commit()
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='Occupations.xlsx'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f'[OCCUPATION] Échec export Excel: {e}')
        logger.error(traceback.format_exc())
        flash('Erreur lors de l\'exportation.', 'danger')
        return redirect(url_for('occupation.list_occupations'))


@occupation.route('/<int:occ_id>/pdf', methods=['POST'])
@login_required
def export_pdf(occ_id):
    occ = _get_occupation_or_404(occ_id)
    try:
        pdf_buffer = generate_occupation_fiche_pdf(occ)
        _log(current_user.id, f'Export PDF occupation: {occ.numero_occupation}', 'occupations', occ.id)
        db.session.commit()
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'{occ.numero_occupation}.pdf'
        )
    except Exception as e:
        logger.error(f'[OCCUPATION] Échec export PDF occ_id={occ_id}: {e}')
        logger.error(traceback.format_exc())
        flash('Erreur lors de la génération du PDF.', 'danger')
        return redirect(url_for('occupation.view_occupation', occ_id=occ_id))
