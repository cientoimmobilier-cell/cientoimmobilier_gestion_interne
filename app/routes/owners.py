from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, send_file, jsonify
from flask_login import login_required, current_user
from app.models import Proprietaire, Propriete
from app.utils.helpers import log_activity, sanitize_search, role_required
from app import db
from datetime import datetime
from app.services.excel_service import export_owners_to_excel, import_owners_from_excel

owners = Blueprint('owners', __name__)

@owners.route('/')
@login_required
def list_owners():
    search = request.args.get('search', '')
    if search:
        safe_search = sanitize_search(search)
        like_pattern = f'%{safe_search}%'
        owners_list = Proprietaire.query.filter(
            (Proprietaire.nom.ilike(like_pattern)) |
            (Proprietaire.prenom.ilike(like_pattern)) |
            (Proprietaire.email.ilike(like_pattern)) |
            (Proprietaire.telephone.ilike(like_pattern))
        ).order_by(Proprietaire.nom.asc()).all()
    else:
        owners_list = Proprietaire.query.order_by(Proprietaire.nom.asc()).all()
        
    return render_template('owners/list.html', owners=owners_list, search=search)

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
            doublon = Proprietaire.query.filter(Proprietaire.telephone == telephone).first()
            if doublon:
                flash(f"⚠️ Doublon détecté : le téléphone <strong>{telephone}</strong> est déjà enregistré pour "
                      f"<a href='{url_for('owners.view_owner', owner_id=doublon.id)}' class='alert-link'>"
                      f"{doublon.prenom} {doublon.nom}</a>.", "danger")
                return render_template('owners/form.html', owner=None, action_title="Ajouter un propriétaire")
        if email:
            doublon = Proprietaire.query.filter(Proprietaire.email == email.lower()).first()
            if doublon:
                flash(f"⚠️ Doublon détecté : l'e-mail <strong>{email}</strong> est déjà enregistré pour "
                      f"<a href='{url_for('owners.view_owner', owner_id=doublon.id)}' class='alert-link'>"
                      f"{doublon.prenom} {doublon.nom}</a>.", "danger")
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
            db.session.commit()
            log_activity(current_user.id, f"Création propriétaire: {new_owner.prenom} {new_owner.nom}", "proprietaires", new_owner.id)
            flash(f"Le propriétaire {new_owner.prenom} {new_owner.nom} a été ajouté avec succès.", "success")
            return redirect(url_for('owners.view_owner', owner_id=new_owner.id))
        except Exception as e:
            db.session.rollback()
            flash("Erreur lors de la création du propriétaire. Veuillez réessayer.", "danger")
            
    return render_template('owners/form.html', owner=None, action_title="Ajouter un propriétaire")

@owners.route('/modifier/<int:owner_id>', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier', 'Assistant')
def edit_owner(owner_id):
    owner_obj = Proprietaire.query.get_or_404(owner_id)
    
    if request.method == 'POST':
        new_telephone = request.form.get('telephone')
        new_email = request.form.get('email')

        # --- Vérification des doublons (exclure l'enregistrement courant) ---
        if new_telephone:
            doublon = Proprietaire.query.filter(Proprietaire.telephone == new_telephone, Proprietaire.id != owner_id).first()
            if doublon:
                flash(f"⚠️ Doublon détecté : le téléphone <strong>{new_telephone}</strong> est déjà enregistré pour "
                      f"<a href='{url_for('owners.view_owner', owner_id=doublon.id)}' class='alert-link'>"
                      f"{doublon.prenom} {doublon.nom}</a>.", "danger")
                return render_template('owners/form.html', owner=owner_obj, action_title=f"Modifier {owner_obj.prenom} {owner_obj.nom}")
        if new_email:
            doublon = Proprietaire.query.filter(Proprietaire.email == new_email.lower(), Proprietaire.id != owner_id).first()
            if doublon:
                flash(f"⚠️ Doublon détecté : l'e-mail <strong>{new_email}</strong> est déjà enregistré pour "
                      f"<a href='{url_for('owners.view_owner', owner_id=doublon.id)}' class='alert-link'>"
                      f"{doublon.prenom} {doublon.nom}</a>.", "danger")
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
            db.session.commit()
            log_activity(current_user.id, f"Modification propriétaire: {owner_obj.prenom} {owner_obj.nom}", "proprietaires", owner_obj.id)
            flash(f"Les informations de {owner_obj.prenom} {owner_obj.nom} ont été mises à jour.", "success")
            return redirect(url_for('owners.view_owner', owner_id=owner_obj.id))
        except Exception as e:
            db.session.rollback()
            flash("Erreur lors de la modification. Veuillez réessayer.", "danger")
            
    return render_template('owners/form.html', owner=owner_obj, action_title=f"Modifier {owner_obj.prenom} {owner_obj.nom}")

@owners.route('/details/<int:owner_id>')
@login_required
def view_owner(owner_id):
    owner_obj = Proprietaire.query.get_or_404(owner_id)
    return render_template('owners/view.html', owner=owner_obj)

@owners.route('/supprimer/<int:owner_id>', methods=['POST'])
@login_required
def delete_owner(owner_id):
    if current_user.role not in ['Administrateur', 'Directeur']:
        abort(403)
        
    owner_obj = Proprietaire.query.get_or_404(owner_id)
    nom_complet = f"{owner_obj.prenom} {owner_obj.nom}"
    
    try:
        db.session.delete(owner_obj)
        db.session.commit()
        log_activity(current_user.id, f"Suppression propriétaire: {nom_complet}", "proprietaires", owner_id)
        flash(f"Le propriétaire {nom_complet} a été supprimé.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Impossible de supprimer ce propriétaire. Veuillez réessayer.", "danger")
        
    return redirect(url_for('owners.list_owners'))


@owners.route('/verifier-doublon')
@login_required
def verifier_doublon_owner():
    """Route AJAX — vérifie si un téléphone ou email est déjà utilisé par un autre propriétaire."""
    telephone = request.args.get('telephone', '').strip()
    email = request.args.get('email', '').strip().lower()
    exclude_id = request.args.get('exclude_id', type=int)

    if telephone:
        q = Proprietaire.query.filter(Proprietaire.telephone == telephone)
        if exclude_id:
            q = q.filter(Proprietaire.id != exclude_id)
        doublon = q.first()
        if doublon:
            return jsonify({
                'doublon': True,
                'champ': 'telephone',
                'nom': f"{doublon.prenom} {doublon.nom}",
                'url': url_for('owners.view_owner', owner_id=doublon.id)
            })

    if email:
        q = Proprietaire.query.filter(Proprietaire.email == email)
        if exclude_id:
            q = q.filter(Proprietaire.id != exclude_id)
        doublon = q.first()
        if doublon:
            return jsonify({
                'doublon': True,
                'champ': 'email',
                'nom': f"{doublon.prenom} {doublon.nom}",
                'url': url_for('owners.view_owner', owner_id=doublon.id)
            })

    return jsonify({'doublon': False})


@owners.route('/exporter')
@login_required
@role_required('Agent immobilier', 'Assistant')
def export_owners():
    owners_list = Proprietaire.query.order_by(Proprietaire.nom.asc()).all()
    excel_file = export_owners_to_excel(owners_list)
    log_activity(current_user.id, "Exportation Excel du portefeuille propriétaires", "proprietaires")
    return send_file(
        excel_file,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="Portefeuille_Proprietaires.xlsx"
    )

@owners.route('/importer', methods=['POST'])
@login_required
def import_owners():
    if current_user.role not in ['Administrateur', 'Directeur']:
        abort(403)
        
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
                existing = Proprietaire.query.filter_by(email=data["email"]).first()
                
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
                
        db.session.commit()
        log_activity(current_user.id, f"Importation Excel propriétaires : {imported_count} créés, {updated_count} mis à jour", "proprietaires")
        flash(f"Importation réussie : {imported_count} propriétaires créés, {updated_count} fiches mises à jour.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de l'importation. Vérifiez le format du fichier.", "danger")
        
    return redirect(url_for('owners.list_owners'))
