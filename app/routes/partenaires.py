import os
import logging
import traceback
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, abort, jsonify
from sqlalchemy import select, func as sa_func
from flask_login import login_required, current_user
from app.models import Partenaire, DocumentPartenaire, CriterePartenaire
from app.utils.helpers import log_activity, sanitize_search, role_required
from app.utils.upload_security import (
    validate_and_save_upload, UploadValidationError, ALLOWED_DOCUMENTS
)
from app import db
from datetime import datetime, date
from markupsafe import Markup, escape

logger = logging.getLogger(__name__)

partenaires = Blueprint('partenaires', __name__)

@partenaires.route('/')
@login_required
@role_required('Agent immobilier')
def list_partenaires():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'nom')
    order = request.args.get('order', 'asc')

    stmt = select(Partenaire)
    if search:
        search_term = f'%{search}%'
        stmt = stmt.where(
            db.or_(Partenaire.nom.ilike(search_term), Partenaire.email.ilike(search_term), Partenaire.telephone.ilike(search_term))
        )

    sort_column = getattr(Partenaire, sort, Partenaire.nom)
    try:
        stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    except:
        stmt = stmt.order_by(Partenaire.nom.asc())

    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    return render_template('partenaires/list.html', pagination=pagination, sort=sort, order=order)

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
            doublon = db.session.execute(select(Partenaire).where(Partenaire.telephone == telephone)).scalars().first()
            if doublon:
                url = url_for('partenaires.view_partenaire', id=doublon.id)
                flash(Markup(
                    f"⚠️ Doublon détecté : le téléphone "
                    f"<strong>{escape(telephone)}</strong> est déjà enregistré pour "
                    f"<a href='{url}' class='alert-link'>"
                    f"{escape(doublon.nom)}</a>."
                ), "danger")
                return render_template('partenaires/form.html', partenaire=None, action_title="Ajouter un partenaire")
        if email:
            doublon = db.session.execute(select(Partenaire).where(Partenaire.email == email.lower())).scalars().first()
            if doublon:
                url = url_for('partenaires.view_partenaire', id=doublon.id)
                flash(Markup(
                    f"⚠️ Doublon détecté : l’e-mail "
                    f"<strong>{escape(email)}</strong> est déjà enregistré pour "
                    f"<a href='{url}' class='alert-link'>"
                    f"{escape(doublon.nom)}</a>."
                ), "danger")
                return render_template('partenaires/form.html', partenaire=None, action_title="Ajouter un partenaire")

        # Validation des dates
        if date_partenariat and date_expiration_contrat:
            try:
                dt_partenariat = datetime.strptime(date_partenariat, "%Y-%m-%d").date() if isinstance(date_partenariat, str) else date_partenariat
                dt_expiration = datetime.strptime(date_expiration_contrat, "%Y-%m-%d").date() if isinstance(date_expiration_contrat, str) else date_expiration_contrat
                if dt_expiration <= dt_partenariat:
                    flash("La date d'expiration du contrat doit être postérieure à la date de partenariat.", "danger")
                    return render_template('partenaires/form.html', partenaire=None, action_title="Ajouter un partenaire")
            except (ValueError, TypeError):
                flash("Format de date invalide.", "danger")
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
            db.session.flush()
            
            documents = request.files.getlist('documents')
            max_size = current_app.config.get('MAX_FILE_SIZE_DOCUMENT', 15 * 1024 * 1024)
            uploaded_docs = []
            
            for doc in documents:
                if not doc or not doc.filename:
                    continue
                try:
                    safe_path, rel_path, unique_name, file_size = validate_and_save_upload(
                        file_storage=doc,
                        upload_subdir='uploads/documents',
                        allowed_extensions=ALLOWED_DOCUMENTS,
                        max_size=max_size,
                        category='document',
                        validate_magic=True,
                        prefix=f"{new_partenaire.id}_",
                        user_id=current_user.id
                    )
                    new_doc = DocumentPartenaire(
                        partenaire_id=new_partenaire.id,
                        nom_document=unique_name,
                        chemin_fichier=rel_path
                    )
                    db.session.add(new_doc)
                    uploaded_docs.append(safe_path)
                except UploadValidationError as e:
                    logger.warning(f"[PARTENAIRES] Document rejeté pour partenaire {new_partenaire.id}: {e.message}")
                    continue
            
            log_activity(current_user.id, f"Création partenaire: {new_partenaire.nom}", "partenaires", new_partenaire.id)
            db.session.commit()
            flash(f"Le partenaire {new_partenaire.nom} a été ajouté avec succès.", "success")
            return redirect(url_for('partenaires.view_partenaire', id=new_partenaire.id))
            
        except Exception as e:
            db.session.rollback()
            for fp in uploaded_docs:
                if os.path.exists(fp):
                    os.remove(fp)
            logger.error(f"[PARTENAIRES] Échec création partenaire par user_id={current_user.id}: {e}")
            logger.error(traceback.format_exc())
            flash("Erreur lors de la création du partenaire. Veuillez vérifier les informations.", "danger")
            
    return render_template('partenaires/form.html', partenaire=None, action_title="Ajouter un partenaire")

@partenaires.route('/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier')
def edit_partenaire(id):
    partenaire_obj = db.session.get(Partenaire, id)
    if partenaire_obj is None:
        abort(404)
    
    if request.method == 'POST':
        new_telephone = request.form.get('telephone')
        new_email = request.form.get('email')

        # --- Vérification des doublons (exclure l'enregistrement courant) ---
        if new_telephone:
            doublon = db.session.execute(select(Partenaire).where(Partenaire.telephone == new_telephone, Partenaire.id != id)).scalars().first()
            if doublon:
                url = url_for('partenaires.view_partenaire', id=doublon.id)
                flash(Markup(
                    f"⚠️ Doublon détecté : le téléphone "
                    f"<strong>{escape(new_telephone)}</strong> est déjà enregistré pour "
                    f"<a href='{url}' class='alert-link'>"
                    f"{escape(doublon.nom)}</a>."
                ), "danger")
                return render_template('partenaires/form.html', partenaire=partenaire_obj, action_title=f"Modifier {partenaire_obj.nom}")
        if new_email:
            doublon = db.session.execute(select(Partenaire).where(Partenaire.email == new_email.lower(), Partenaire.id != id)).scalars().first()
            if doublon:
                url = url_for('partenaires.view_partenaire', id=doublon.id)
                flash(Markup(
                    f"⚠️ Doublon détecté : l’e-mail "
                    f"<strong>{escape(new_email)}</strong> est déjà enregistré pour "
                    f"<a href='{url}' class='alert-link'>"
                    f"{escape(doublon.nom)}</a>."
                ), "danger")
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
            documents = request.files.getlist('documents')
            max_size = current_app.config.get('MAX_FILE_SIZE_DOCUMENT', 15 * 1024 * 1024)
            uploaded_docs = []
            
            for doc in documents:
                if not doc or not doc.filename:
                    continue
                try:
                    safe_path, rel_path, unique_name, file_size = validate_and_save_upload(
                        file_storage=doc,
                        upload_subdir='uploads/documents',
                        allowed_extensions=ALLOWED_DOCUMENTS,
                        max_size=max_size,
                        category='document',
                        validate_magic=True,
                        prefix=f"{partenaire_obj.id}_",
                        user_id=current_user.id
                    )
                    new_doc = DocumentPartenaire(
                        partenaire_id=partenaire_obj.id,
                        nom_document=unique_name,
                        chemin_fichier=rel_path
                    )
                    db.session.add(new_doc)
                    uploaded_docs.append(safe_path)
                except UploadValidationError as e:
                    logger.warning(f"[PARTENAIRES] Document rejeté pour partenaire {partenaire_obj.id}: {e.message}")
                    continue
                    
            log_activity(current_user.id, f"Modification partenaire: {partenaire_obj.nom}", "partenaires", partenaire_obj.id)
            db.session.commit()
            flash(f"Les informations de {partenaire_obj.nom} ont été mises à jour.", "success")
            return redirect(url_for('partenaires.view_partenaire', id=partenaire_obj.id))
        except Exception as e:
            db.session.rollback()
            for fp in uploaded_docs:
                if os.path.exists(fp):
                    os.remove(fp)
            logger.error(f"[PARTENAIRES] Échec modification partenaire id={id}: {e}")
            logger.error(traceback.format_exc())
            flash("Erreur lors de la modification. Veuillez réessayer.", "danger")
            
    return render_template('partenaires/form.html', partenaire=partenaire_obj, action_title=f"Modifier {partenaire_obj.nom}")

@partenaires.route('/details/<int:id>')
@login_required
@role_required('Agent immobilier')
def view_partenaire(id):
    partenaire_obj = db.session.get(Partenaire, id)
    if partenaire_obj is None:
        abort(404)
    return render_template('partenaires/view.html', partenaire=partenaire_obj)

@partenaires.route('/supprimer/<int:id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def delete_partenaire(id):
    partenaire_obj = db.session.get(Partenaire, id)
    if partenaire_obj is None:
        abort(404)
    nom = partenaire_obj.nom
    
    try:
        db.session.delete(partenaire_obj)
        log_activity(current_user.id, f"Suppression partenaire: {nom}", "partenaires", id)
        db.session.commit()
        flash(f"Le partenaire {nom} a été supprimé.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[PARTENAIRES] Échec suppression partenaire id={id}: {e}")
        logger.error(traceback.format_exc())
        flash("Impossible de supprimer ce partenaire. Veuillez réessayer.", "danger")
        
    return redirect(url_for('partenaires.list_partenaires'))


@partenaires.route('/verifier-doublon')
@login_required
def verifier_doublon_partenaire():
    """Route AJAX — vérifie si un téléphone ou email est déjà utilisé par un autre partenaire."""
    try:
        telephone = request.args.get('telephone', '').strip()
        email = request.args.get('email', '').strip().lower()
        exclude_id = request.args.get('exclude_id', type=int)

        if telephone:
            stmt = select(Partenaire).where(Partenaire.telephone == telephone)
            if exclude_id:
                stmt = stmt.where(Partenaire.id != exclude_id)
            doublon = db.session.execute(stmt).scalars().first()
            if doublon:
                return jsonify({
                    'doublon': True,
                    'champ': 'telephone',
                    'nom': doublon.nom,
                    'url': url_for('partenaires.view_partenaire', id=doublon.id)
                })

        if email:
            stmt = select(Partenaire).where(Partenaire.email == email)
            if exclude_id:
                stmt = stmt.where(Partenaire.id != exclude_id)
            doublon = db.session.execute(stmt).scalars().first()
            if doublon:
                return jsonify({
                    'doublon': True,
                    'champ': 'email',
                    'nom': doublon.nom,
                    'url': url_for('partenaires.view_partenaire', id=doublon.id)
                })

        return jsonify({'doublon': False})
    except Exception as e:
        logger.error(f"[PARTENAIRES] Erreur vérification doublon: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'doublon': False, 'error': 'Erreur interne'}), 500


@partenaires.route('/document/supprimer/<int:doc_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def delete_document(doc_id):
    doc = db.session.get(DocumentPartenaire, doc_id)
    if doc is None:
        abort(404)
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
        log_activity(current_user.id, f"Suppression document partenaire", "documents_partenaires", doc_id)
        db.session.commit()
        flash("Document supprimé avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[PARTENAIRES] Échec suppression document id={doc_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la suppression du document.", "danger")
        
    return redirect(url_for('partenaires.view_partenaire', id=partenaire_id))

@partenaires.route('/criteres/ajouter/<int:partenaire_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def add_critere(partenaire_id):
    partenaire = db.session.get(Partenaire, partenaire_id)
    if partenaire is None:
        abort(404)
    
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
        log_activity(current_user.id, f"Ajout critère pour partenaire: {partenaire.nom}", "criteres_partenaires", nouveau_critere.id)
        db.session.commit()
        flash("Le critère a été ajouté avec succès.", "success")
    except ValueError:
        flash("La commission doit être un nombre valide.", "danger")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[PARTENAIRES] Échec ajout critère pour partenaire_id={partenaire_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'ajout du critère.", "danger")
        
    return redirect(url_for('partenaires.view_partenaire', id=partenaire_id))

@partenaires.route('/criteres/supprimer/<int:critere_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def delete_critere(critere_id):
    critere = db.session.get(CriterePartenaire, critere_id)
    if critere is None:
        abort(404)
    partenaire_id = critere.partenaire_id
    
    try:
        db.session.delete(critere)
        log_activity(current_user.id, "Suppression critère partenaire", "criteres_partenaires", critere_id)
        db.session.commit()
        flash("Le critère a été supprimé.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[PARTENAIRES] Échec suppression critère id={critere_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la suppression du critère.", "danger")
        
    return redirect(url_for('partenaires.view_partenaire', id=partenaire_id))
