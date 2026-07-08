import os
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, abort, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models import Partenaire, DocumentPartenaire, CriterePartenaire
from app.utils.helpers import log_activity, sanitize_search, role_required
from app import db
from datetime import datetime

partenaires = Blueprint('partenaires', __name__)

@partenaires.route('/')
@login_required
@role_required('Agent immobilier')
def list_partenaires():
    search = request.args.get('search', '')
    if search:
        safe_search = sanitize_search(search)
        like_pattern = f'%{safe_search}%'
        partenaires_list = Partenaire.query.filter(
            (Partenaire.nom.ilike(like_pattern)) |
            (Partenaire.numero_identification.ilike(like_pattern)) |
            (Partenaire.email.ilike(like_pattern))
        ).order_by(Partenaire.nom.asc()).all()
    else:
        partenaires_list = Partenaire.query.order_by(Partenaire.nom.asc()).all()
        
    return render_template('partenaires/list.html', partenaires=partenaires_list, search=search)

@partenaires.route('/ajouter', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier')
def add_partenaire():
    if request.method == 'POST':
        nom = request.form.get('nom')
        email = request.form.get('email')
        telephone = request.form.get('telephone')
        numero_identification = request.form.get('numero_identification')
        numero_fiscal = request.form.get('numero_fiscal')
        date_partenariat = request.form.get('date_partenariat')
        contrat_signe = request.form.get('contrat_signe') == 'on'
        date_expiration_contrat = request.form.get('date_expiration_contrat')
        
        # Convert empty strings to None for dates
        date_partenariat = date_partenariat if date_partenariat else None
        date_expiration_contrat = date_expiration_contrat if date_expiration_contrat else None
        
        # --- Vérification des doublons ---
        if telephone:
            doublon = Partenaire.query.filter(Partenaire.telephone == telephone).first()
            if doublon:
                flash(f"⚠️ Doublon détecté : le téléphone <strong>{telephone}</strong> est déjà enregistré pour "
                      f"<a href='{url_for('partenaires.view_partenaire', id=doublon.id)}' class='alert-link'>"
                      f"{doublon.nom}</a>.", "danger")
                return render_template('partenaires/form.html', partenaire=None, action_title="Ajouter un partenaire")
        if email:
            doublon = Partenaire.query.filter(Partenaire.email == email.lower()).first()
            if doublon:
                flash(f"⚠️ Doublon détecté : l'e-mail <strong>{email}</strong> est déjà enregistré pour "
                      f"<a href='{url_for('partenaires.view_partenaire', id=doublon.id)}' class='alert-link'>"
                      f"{doublon.nom}</a>.", "danger")
                return render_template('partenaires/form.html', partenaire=None, action_title="Ajouter un partenaire")

        new_partenaire = Partenaire(
            nom=nom,
            email=email,
            telephone=telephone,
            numero_identification=numero_identification,
            numero_fiscal=numero_fiscal,
            date_partenariat=date_partenariat,
            contrat_signe=contrat_signe,
            date_expiration_contrat=date_expiration_contrat
        )
        
        try:
            db.session.add(new_partenaire)
            db.session.flush() # To get the new_partenaire.id
            
            # Handle document uploads
            documents = request.files.getlist('documents')
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'documents')
            os.makedirs(upload_dir, exist_ok=True)
            
            for doc in documents:
                if doc and doc.filename:
                    filename = secure_filename(doc.filename)
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    unique_filename = f"{timestamp}_{new_partenaire.id}_{filename}"
                    file_path = os.path.join(upload_dir, unique_filename)
                    
                    doc.save(file_path)
                    
                    new_doc = DocumentPartenaire(
                        partenaire_id=new_partenaire.id,
                        nom_document=filename,
                        chemin_fichier=os.path.join('uploads', 'documents', unique_filename).replace('\\', '/')
                    )
                    db.session.add(new_doc)
            
            db.session.commit()
            log_activity(current_user.id, f"Création partenaire: {new_partenaire.nom}", "partenaires", new_partenaire.id)
            flash(f"Le partenaire {new_partenaire.nom} a été ajouté avec succès.", "success")
            return redirect(url_for('partenaires.view_partenaire', id=new_partenaire.id))
            
        except Exception as e:
            db.session.rollback()
            flash("Erreur lors de la création du partenaire. Veuillez vérifier les informations.", "danger")
            
    return render_template('partenaires/form.html', partenaire=None, action_title="Ajouter un partenaire")

@partenaires.route('/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier')
def edit_partenaire(id):
    partenaire_obj = Partenaire.query.get_or_404(id)
    
    if request.method == 'POST':
        new_telephone = request.form.get('telephone')
        new_email = request.form.get('email')

        # --- Vérification des doublons (exclure l'enregistrement courant) ---
        if new_telephone:
            doublon = Partenaire.query.filter(Partenaire.telephone == new_telephone, Partenaire.id != id).first()
            if doublon:
                flash(f"⚠️ Doublon détecté : le téléphone <strong>{new_telephone}</strong> est déjà enregistré pour "
                      f"<a href='{url_for('partenaires.view_partenaire', id=doublon.id)}' class='alert-link'>"
                      f"{doublon.nom}</a>.", "danger")
                return render_template('partenaires/form.html', partenaire=partenaire_obj, action_title=f"Modifier {partenaire_obj.nom}")
        if new_email:
            doublon = Partenaire.query.filter(Partenaire.email == new_email.lower(), Partenaire.id != id).first()
            if doublon:
                flash(f"⚠️ Doublon détecté : l'e-mail <strong>{new_email}</strong> est déjà enregistré pour "
                      f"<a href='{url_for('partenaires.view_partenaire', id=doublon.id)}' class='alert-link'>"
                      f"{doublon.nom}</a>.", "danger")
                return render_template('partenaires/form.html', partenaire=partenaire_obj, action_title=f"Modifier {partenaire_obj.nom}")

        partenaire_obj.nom = request.form.get('nom')
        partenaire_obj.email = new_email
        partenaire_obj.telephone = new_telephone
        partenaire_obj.numero_identification = request.form.get('numero_identification')
        partenaire_obj.numero_fiscal = request.form.get('numero_fiscal')
        
        date_partenariat = request.form.get('date_partenariat')
        date_expiration_contrat = request.form.get('date_expiration_contrat')
        partenaire_obj.date_partenariat = date_partenariat if date_partenariat else None
        partenaire_obj.date_expiration_contrat = date_expiration_contrat if date_expiration_contrat else None
        partenaire_obj.contrat_signe = request.form.get('contrat_signe') == 'on'
        
        try:
            # Handle new document uploads
            documents = request.files.getlist('documents')
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'documents')
            os.makedirs(upload_dir, exist_ok=True)
            
            for doc in documents:
                if doc and doc.filename:
                    filename = secure_filename(doc.filename)
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    unique_filename = f"{timestamp}_{partenaire_obj.id}_{filename}"
                    file_path = os.path.join(upload_dir, unique_filename)
                    
                    doc.save(file_path)
                    
                    new_doc = DocumentPartenaire(
                        partenaire_id=partenaire_obj.id,
                        nom_document=filename,
                        chemin_fichier=os.path.join('uploads', 'documents', unique_filename).replace('\\', '/')
                    )
                    db.session.add(new_doc)
                    
            db.session.commit()
            log_activity(current_user.id, f"Modification partenaire: {partenaire_obj.nom}", "partenaires", partenaire_obj.id)
            flash(f"Les informations de {partenaire_obj.nom} ont été mises à jour.", "success")
            return redirect(url_for('partenaires.view_partenaire', id=partenaire_obj.id))
        except Exception as e:
            db.session.rollback()
            flash("Erreur lors de la modification. Veuillez réessayer.", "danger")
            
    return render_template('partenaires/form.html', partenaire=partenaire_obj, action_title=f"Modifier {partenaire_obj.nom}")

@partenaires.route('/details/<int:id>')
@login_required
@role_required('Agent immobilier')
def view_partenaire(id):
    partenaire_obj = Partenaire.query.get_or_404(id)
    return render_template('partenaires/view.html', partenaire=partenaire_obj)

@partenaires.route('/supprimer/<int:id>', methods=['POST'])
@login_required
def delete_partenaire(id):
    if current_user.role not in ['Administrateur', 'Directeur']:
        abort(403)
        
    partenaire_obj = Partenaire.query.get_or_404(id)
    nom = partenaire_obj.nom
    
    try:
        db.session.delete(partenaire_obj)
        db.session.commit()
        log_activity(current_user.id, f"Suppression partenaire: {nom}", "partenaires", id)
        flash(f"Le partenaire {nom} a été supprimé.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Impossible de supprimer ce partenaire. Veuillez réessayer.", "danger")
        
    return redirect(url_for('partenaires.list_partenaires'))


@partenaires.route('/verifier-doublon')
@login_required
def verifier_doublon_partenaire():
    """Route AJAX — vérifie si un téléphone ou email est déjà utilisé par un autre partenaire."""
    telephone = request.args.get('telephone', '').strip()
    email = request.args.get('email', '').strip().lower()
    exclude_id = request.args.get('exclude_id', type=int)

    if telephone:
        q = Partenaire.query.filter(Partenaire.telephone == telephone)
        if exclude_id:
            q = q.filter(Partenaire.id != exclude_id)
        doublon = q.first()
        if doublon:
            return jsonify({
                'doublon': True,
                'champ': 'telephone',
                'nom': doublon.nom,
                'url': url_for('partenaires.view_partenaire', id=doublon.id)
            })

    if email:
        q = Partenaire.query.filter(Partenaire.email == email)
        if exclude_id:
            q = q.filter(Partenaire.id != exclude_id)
        doublon = q.first()
        if doublon:
            return jsonify({
                'doublon': True,
                'champ': 'email',
                'nom': doublon.nom,
                'url': url_for('partenaires.view_partenaire', id=doublon.id)
            })

    return jsonify({'doublon': False})


@partenaires.route('/document/supprimer/<int:doc_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def delete_document(doc_id):
    doc = DocumentPartenaire.query.get_or_404(doc_id)
    partenaire_id = doc.partenaire_id
    
    try:
        # Delete file from filesystem
        base_dir = os.path.dirname(current_app.config['UPLOAD_FOLDER']) # To get the app root if UPLOAD_FOLDER is static/uploads
        # Ensure we are handling paths correctly
        if doc.chemin_fichier.startswith('uploads/'):
            file_path = os.path.join(current_app.static_folder, doc.chemin_fichier)
            if os.path.exists(file_path):
                os.remove(file_path)
                
        db.session.delete(doc)
        db.session.commit()
        log_activity(current_user.id, f"Suppression document partenaire", "documents_partenaires", doc_id)
        flash("Document supprimé avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de la suppression du document.", "danger")
        
    return redirect(url_for('partenaires.view_partenaire', id=partenaire_id))

@partenaires.route('/criteres/ajouter/<int:partenaire_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def add_critere(partenaire_id):
    partenaire = Partenaire.query.get_or_404(partenaire_id)
    
    nom_critere = request.form.get('nom_critere')
    commission = request.form.get('commission')
    devise = request.form.get('devise', 'EUR')
    options = request.form.get('options_supplementaires')
    
    if not nom_critere:
        flash("Le nom du critère est obligatoire.", "danger")
        return redirect(url_for('partenaires.view_partenaire', id=partenaire_id))
        
    try:
        if commission:
            commission = float(commission)
        else:
            commission = None
            
        nouveau_critere = CriterePartenaire(
            partenaire_id=partenaire_id,
            nom_critere=nom_critere,
            commission=commission,
            devise=devise,
            options_supplementaires=options
        )
        
        db.session.add(nouveau_critere)
        db.session.commit()
        log_activity(current_user.id, f"Ajout critère pour partenaire: {partenaire.nom}", "criteres_partenaires", nouveau_critere.id)
        flash("Le critère a été ajouté avec succès.", "success")
    except ValueError:
        flash("La commission doit être un nombre valide.", "danger")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de l'ajout du critère.", "danger")
        
    return redirect(url_for('partenaires.view_partenaire', id=partenaire_id))

@partenaires.route('/criteres/supprimer/<int:critere_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def delete_critere(critere_id):
    critere = CriterePartenaire.query.get_or_404(critere_id)
    partenaire_id = critere.partenaire_id
    
    try:
        db.session.delete(critere)
        db.session.commit()
        log_activity(current_user.id, "Suppression critère partenaire", "criteres_partenaires", critere_id)
        flash("Le critère a été supprimé.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de la suppression du critère.", "danger")
        
    return redirect(url_for('partenaires.view_partenaire', id=partenaire_id))
