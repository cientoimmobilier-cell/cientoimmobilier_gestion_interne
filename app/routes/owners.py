import logging
import traceback
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, send_file, jsonify
from sqlalchemy import select, func as sa_func
from flask_login import login_required, current_user
from app.models import Proprietaire, Propriete
from app.utils.helpers import log_activity, sanitize_search, role_required
from app import db
from markupsafe import Markup, escape
from app.services.excel_service import export_owners_to_excel, import_owners_from_excel

logger = logging.getLogger(__name__)

owners = Blueprint('owners', __name__)

@owners.route('/')
@login_required
def list_owners():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'nom')
    order = request.args.get('order', 'asc')

    stmt = select(Proprietaire)

    if search:
        safe_search = sanitize_search(search)
        like_pattern = f'%{safe_search}%'
        stmt = stmt.where(
            db.or_(
                Proprietaire.nom.ilike(like_pattern),
                Proprietaire.prenom.ilike(like_pattern),
                Proprietaire.email.ilike(like_pattern),
                Proprietaire.telephone.ilike(like_pattern)
            )
        )

    sort_column = getattr(Proprietaire, sort, Proprietaire.nom)
    try:
        stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    except:
        stmt = stmt.order_by(Proprietaire.nom.asc())

    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    return render_template('owners/list.html', owners=pagination.items, pagination=pagination, search=search, sort=sort, order=order)

@owners.route('/ajouter', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier', 'Assistant')
def add_owner():
    if request.method == 'POST':
        nom = request.form.get('nom')
        prenom = request.form.get('prenom')
        telephone = request.form.get('telephone')
        email = request.form.get('email')
        adresse = request.form.get('adresse')
        numero_identite = request.form.get('numero_identite')
        observations = request.form.get('observations')
        
        # --- Vérification des doublons ---
        if telephone:
            doublon = db.session.execute(select(Proprietaire).where(Proprietaire.telephone == telephone)).scalars().first()
            if doublon:
                url = url_for('owners.view_owner', owner_id=doublon.id)
                flash(Markup(
                    f"⚠️ Doublon détecté : le téléphone "
                    f"<strong>{escape(telephone)}</strong> est déjà enregistré pour "
                    f"<a href='{url}' class='alert-link'>"
                    f"{escape(doublon.prenom)} {escape(doublon.nom)}</a>."
                ), "danger")
                return render_template('owners/form.html', owner=None, action_title="Ajouter un propriétaire")
        if email:
            doublon = db.session.execute(select(Proprietaire).where(Proprietaire.email == email.lower())).scalars().first()
            if doublon:
                url = url_for('owners.view_owner', owner_id=doublon.id)
                flash(Markup(
                    f"⚠️ Doublon détecté : l’e-mail "
                    f"<strong>{escape(email)}</strong> est déjà enregistré pour "
                    f"<a href='{url}' class='alert-link'>"
                    f"{escape(doublon.prenom)} {escape(doublon.nom)}</a>."
                ), "danger")
                return render_template('owners/form.html', owner=None, action_title="Ajouter un propriétaire")

        # Validation des champs obligatoires
        if not nom or not nom.strip():
            flash("Le nom de famille est obligatoire.", "danger")
            return render_template('owners/form.html', owner=None, action_title="Ajouter un propriétaire")
        if not prenom or not prenom.strip():
            flash("Le prénom est obligatoire.", "danger")
            return render_template('owners/form.html', owner=None, action_title="Ajouter un propriétaire")

        new_owner = Proprietaire(
            nom=nom.strip().upper(),
            prenom=prenom.strip().title(),
            telephone=telephone,
            email=email.strip().lower() if email else None,
            adresse=adresse,
            numero_identite=numero_identite,
            observations=observations
        )
        
        try:
            db.session.add(new_owner)
            log_activity(current_user.id, f"Création propriétaire: {new_owner.prenom} {new_owner.nom}", "proprietaires", new_owner.id)
            db.session.commit()
            flash(f"Le propriétaire {new_owner.prenom} {new_owner.nom} a été ajouté avec succès.", "success")
            return redirect(url_for('owners.view_owner', owner_id=new_owner.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"[OWNERS] Échec création propriétaire par user_id={current_user.id}: {e}")
            logger.error(traceback.format_exc())
            flash("Erreur lors de la création du propriétaire. Veuillez réessayer.", "danger")
            
    return render_template('owners/form.html', owner=None, action_title="Ajouter un propriétaire")

@owners.route('/modifier/<int:owner_id>', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier', 'Assistant')
def edit_owner(owner_id):
    owner_obj = db.session.get(Proprietaire, owner_id)
    if owner_obj is None:
        abort(404)
    
    if request.method == 'POST':
        new_telephone = request.form.get('telephone')
        new_email = request.form.get('email')

        # --- Vérification des doublons (exclure l'enregistrement courant) ---
        if new_telephone:
            doublon = db.session.execute(select(Proprietaire).where(Proprietaire.telephone == new_telephone, Proprietaire.id != owner_id)).scalars().first()
            if doublon:
                url = url_for('owners.view_owner', owner_id=doublon.id)
                flash(Markup(
                    f"⚠️ Doublon détecté : le téléphone "
                    f"<strong>{escape(new_telephone)}</strong> est déjà enregistré pour "
                    f"<a href='{url}' class='alert-link'>"
                    f"{escape(doublon.prenom)} {escape(doublon.nom)}</a>."
                ), "danger")
                return render_template('owners/form.html', owner=owner_obj, action_title=f"Modifier {owner_obj.prenom} {owner_obj.nom}")
        if new_email:
            doublon = db.session.execute(select(Proprietaire).where(Proprietaire.email == new_email.lower(), Proprietaire.id != owner_id)).scalars().first()
            if doublon:
                url = url_for('owners.view_owner', owner_id=doublon.id)
                flash(Markup(
                    f"⚠️ Doublon détecté : l’e-mail "
                    f"<strong>{escape(new_email)}</strong> est déjà enregistré pour "
                    f"<a href='{url}' class='alert-link'>"
                    f"{escape(doublon.prenom)} {escape(doublon.nom)}</a>."
                ), "danger")
                return render_template('owners/form.html', owner=owner_obj, action_title=f"Modifier {owner_obj.prenom} {owner_obj.nom}")

        nom_edit = request.form.get('nom', '').strip()
        prenom_edit = request.form.get('prenom', '').strip()
        if not nom_edit or not prenom_edit:
            flash("Le nom et le prénom sont obligatoires.", "danger")
            return render_template('owners/form.html', owner=owner_obj, action_title=f"Modifier {owner_obj.prenom} {owner_obj.nom}")
        owner_obj.nom = nom_edit.upper()
        owner_obj.prenom = prenom_edit.title()
        owner_obj.telephone = new_telephone
        owner_obj.email = new_email.strip().lower() if new_email else None
        owner_obj.adresse = request.form.get('adresse')
        owner_obj.numero_identite = request.form.get('numero_identite')
        owner_obj.observations = request.form.get('observations')
        
        try:
            log_activity(current_user.id, f"Modification propriétaire: {owner_obj.prenom} {owner_obj.nom}", "proprietaires", owner_obj.id)
            db.session.commit()
            flash(f"Les informations de {owner_obj.prenom} {owner_obj.nom} ont été mises à jour.", "success")
            return redirect(url_for('owners.view_owner', owner_id=owner_obj.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"[OWNERS] Échec modification propriétaire id={owner_id}: {e}")
            logger.error(traceback.format_exc())
            flash("Erreur lors de la modification. Veuillez réessayer.", "danger")
            
    return render_template('owners/form.html', owner=owner_obj, action_title=f"Modifier {owner_obj.prenom} {owner_obj.nom}")

@owners.route('/details/<int:owner_id>')
@login_required
def view_owner(owner_id):
    owner_obj = db.session.get(Proprietaire, owner_id)
    if owner_obj is None:
        abort(404)
    return render_template('owners/view.html', owner=owner_obj)

@owners.route('/supprimer/<int:owner_id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def delete_owner(owner_id):
    owner_obj = db.session.get(Proprietaire, owner_id)
    if owner_obj is None:
        abort(404)
    nom_complet = f"{owner_obj.prenom} {owner_obj.nom}"
    
    # Vérifier les dépendances : propriétés actives liées
    proprietes_liees = [p for p in owner_obj.proprietes if p.statut not in ('Vendu', 'Loué')]
    if proprietes_liees:
        flash(
            f"Impossible de supprimer {nom_complet} : {len(proprietes_liees)} propriété(s) encore actives "
            f"lui sont associées. Réaffectez d'abord ces propriétés.",
            "danger"
        )
        return redirect(url_for('owners.view_owner', owner_id=owner_id))
    
    try:
        db.session.delete(owner_obj)
        log_activity(current_user.id, f"Suppression propriétaire: {nom_complet}", "proprietaires", owner_id)
        db.session.commit()
        flash(f"Le propriétaire {nom_complet} a été supprimé.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[OWNERS] Échec suppression propriétaire id={owner_id} par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Impossible de supprimer ce propriétaire. Veuillez réessayer.", "danger")
        
    return redirect(url_for('owners.list_owners'))


@owners.route('/verifier-doublon')
@login_required
def verifier_doublon_owner():
    """Route AJAX — vérifie si un téléphone ou email est déjà utilisé par un autre propriétaire."""
    try:
        telephone = request.args.get('telephone', '').strip()
        email = request.args.get('email', '').strip().lower()
        exclude_id = request.args.get('exclude_id', type=int)

        if telephone:
            stmt = select(Proprietaire).where(Proprietaire.telephone == telephone)
            if exclude_id:
                stmt = stmt.where(Proprietaire.id != exclude_id)
            doublon = db.session.execute(stmt).scalars().first()
            if doublon:
                return jsonify({
                    'doublon': True,
                    'champ': 'telephone',
                    'nom': f"{doublon.prenom} {doublon.nom}",
                    'url': url_for('owners.view_owner', owner_id=doublon.id)
                })

        if email:
            stmt = select(Proprietaire).where(Proprietaire.email == email)
            if exclude_id:
                stmt = stmt.where(Proprietaire.id != exclude_id)
            doublon = db.session.execute(stmt).scalars().first()
            if doublon:
                return jsonify({
                    'doublon': True,
                    'champ': 'email',
                    'nom': f"{doublon.prenom} {doublon.nom}",
                    'url': url_for('owners.view_owner', owner_id=doublon.id)
                })

        return jsonify({'doublon': False})
    except Exception as e:
        logger.error(f"[OWNERS] Erreur vérification doublon: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'doublon': False, 'error': 'Erreur interne'}), 500


@owners.route('/exporter', methods=['POST'])
@login_required
@role_required('Agent immobilier', 'Assistant')
def export_owners():
    try:
        owners_list = db.session.execute(select(Proprietaire).order_by(Proprietaire.nom.asc())).scalars().all()
        excel_file = export_owners_to_excel(owners_list)
        log_activity(current_user.id, "Exportation Excel du portefeuille propriétaires", "proprietaires")
        db.session.commit()
        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="Portefeuille_Proprietaires.xlsx"
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"[OWNERS] Échec export Excel par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'exportation. Veuillez réessayer.", "danger")
        return redirect(url_for('owners.list_owners'))

@owners.route('/importer', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def import_owners():
    if 'excel_file' not in request.files:
        flash("Aucun fichier envoyé.", "warning")
        return redirect(url_for('owners.list_owners'))
        
    file = request.files['excel_file']
    if not file or file.filename == '':
        flash("Fichier invalide.", "warning")
        return redirect(url_for('owners.list_owners'))
        
    try:
        owners_data = import_owners_from_excel(file)
        imported_count = 0
        updated_count = 0
        
        for data in owners_data:
            existing = None
            if data["email"]:
                existing = db.session.execute(select(Proprietaire).where(Proprietaire.email == data["email"])).scalars().first()
                
            if existing:
                existing.nom = data["nom"]
                existing.prenom = data["prenom"]
                existing.telephone = data["telephone"]
                existing.adresse = data["adresse"]
                existing.numero_identite = data["numero_identite"]
                existing.observations = data["observations"]
                updated_count += 1
            else:
                new_owner = Proprietaire(
                    nom=data["nom"],
                    prenom=data["prenom"],
                    telephone=data["telephone"],
                    email=data["email"],
                    adresse=data["adresse"],
                    numero_identite=data["numero_identite"],
                    observations=data["observations"]
                )
                db.session.add(new_owner)
                db.session.flush()
                imported_count += 1
                
        log_activity(current_user.id, f"Importation Excel propriétaires : {imported_count} créés, {updated_count} mis à jour", "proprietaires")
        db.session.commit()
        flash(f"Importation réussie : {imported_count} propriétaires créés, {updated_count} fiches mises à jour.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[OWNERS] Échec import Excel par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'importation. Vérifiez le format du fichier Excel.", "danger")
        
    return redirect(url_for('owners.list_owners'))
