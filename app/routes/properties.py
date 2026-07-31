import logging
import traceback
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, current_app, send_file
from flask_login import login_required, current_user
from app.models import (Propriete, Proprietaire, Caracteristique, PhotoPropriete, 
                        DocumentPropriete, Visite, Client, Utilisateur)
from app.utils.helpers import log_activity, role_required, sanitize_search, safe_path_join
from app.utils.upload_security import (
    validate_and_save_upload,
    validate_excel_content,
    check_file_size_before_read, check_blocked_extension,
    UploadValidationError,
    ALLOWED_IMAGES, ALLOWED_DOCUMENTS
)
from app import db
from sqlalchemy import select, update, func as sa_func
from datetime import datetime, timezone, date
import os
from app.services.excel_service import export_properties_to_excel, import_properties_from_excel

logger = logging.getLogger(__name__)

properties = Blueprint('properties', __name__)

@properties.route('/')
@login_required
def list_properties():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'date_ajout')
    order = request.args.get('order', 'desc')
    type_bien = request.args.get('type_bien', '')
    statut = request.args.get('statut', '')
    prix_max = request.args.get('prix_max', '')
    
    stmt = select(Propriete)
    
    if search:
        safe_search = sanitize_search(search)
        like_pattern = f'%{safe_search}%'
        stmt = stmt.where(
            (Propriete.reference_bien.ilike(like_pattern)) |
            (Propriete.titre.ilike(like_pattern)) |
            (Propriete.ville.ilike(like_pattern)) |
            (Propriete.quartier.ilike(like_pattern))
        )
    if type_bien:
        stmt = stmt.where(Propriete.type_bien == type_bien)
    if statut:
        stmt = stmt.where(Propriete.statut == statut)
    if prix_max:
        try:
            stmt = stmt.where(Propriete.prix <= float(prix_max))
        except ValueError:
            pass
    
    sort_column = getattr(Propriete, sort, Propriete.date_ajout)
    try:
        stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    except:
        stmt = stmt.order_by(Propriete.date_ajout.desc())
    
    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    
    property_types = ['Maison', 'Appartement', 'Terrain', 'Villa', 'Bureau', 'Local commercial', 'Entrepôt', 'Immeuble']
    
    return render_template(
        'properties/list.html', 
        pagination=pagination,
        properties=pagination.items,
        property_types=property_types,
        search=search,
        type_bien=type_bien,
        statut=statut,
        prix_max=prix_max,
        sort=sort,
        order=order,
        per_page=per_page
    )

@properties.route('/ajouter', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier')
def add_property():
    proprietaires = db.session.execute(select(Proprietaire).order_by(Proprietaire.nom.asc())).scalars().all()
    caracteristiques = db.session.execute(select(Caracteristique).order_by(Caracteristique.nom.asc())).scalars().all()
    
    if request.method == 'POST':
        titre = request.form.get('titre')
        proprietaire_id = request.form.get('proprietaire_id') or None
        description = request.form.get('description')
        type_bien = request.form.get('type_bien')
        type_operation = request.form.get('type_operation')
        adresse = request.form.get('adresse')
        ville = request.form.get('ville')
        quartier = request.form.get('quartier')
        prix = request.form.get('prix')
        superficie = request.form.get('superficie') or None
        chambres = request.form.get('nombre_chambres') or None
        salles_bain = request.form.get('nombre_salles_bain') or None
        garages = request.form.get('nombre_garages') or None
        statut = request.form.get('statut', 'Disponible')
        devise = request.form.get('devise', 'EUR')
        
        # Caractéristiques choisies
        selected_caracs = request.form.getlist('caracteristiques')
        
        # Générer la référence unique
        count = db.session.execute(select(sa_func.count(Propriete.id))).scalar()
        reference_bien = f"BIEN-{datetime.now(timezone.utc).year}-{count + 1:04d}"
        
        new_prop = Propriete(
            reference_bien=reference_bien,
            proprietaire_id=proprietaire_id,
            titre=titre,
            description=description,
            type_bien=type_bien,
            type_operation=type_operation,
            adresse=adresse,
            ville=ville,
            quartier=quartier,
            prix=prix,
            devise=devise,
            superficie=superficie,
            nombre_chambres=chambres,
            nombre_salles_bain=salles_bain,
            nombre_garages=garages,
            statut=statut
        )
        
        # Associer les caractéristiques
        for c_id in selected_caracs:
            carac = db.session.get(Caracteristique, int(c_id))
            if carac:
                new_prop.caracteristiques.append(carac)
                
        try:
            db.session.add(new_prop)
            log_activity(current_user.id, f"Création propriété: {reference_bien}", "proprietes", new_prop.id)
            db.session.commit()
            flash(f"La propriété {reference_bien} a été ajoutée avec succès.", "success")
            return redirect(url_for('properties.view_property', property_id=new_prop.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"[PROPRIETES] Échec création propriété par user_id={current_user.id}: {e}")
            logger.error(traceback.format_exc())
            flash("Erreur lors de la création de la propriété. Veuillez réessayer.", "danger")
            
    return render_template('properties/form.html', property=None, proprietaires=proprietaires, caracteristiques=caracteristiques, action_title="Ajouter une propriété")

@properties.route('/modifier/<int:property_id>', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier')
def edit_property(property_id):
    prop = db.session.get(Propriete, property_id)
    if prop is None:
        abort(404)
    proprietaires = db.session.execute(select(Proprietaire).order_by(Proprietaire.nom.asc())).scalars().all()
    caracteristiques = db.session.execute(select(Caracteristique).order_by(Caracteristique.nom.asc())).scalars().all()
    
    if request.method == 'POST':
        prop.titre = request.form.get('titre')
        prop.proprietaire_id = request.form.get('proprietaire_id') or None
        prop.description = request.form.get('description')
        prop.type_bien = request.form.get('type_bien')
        prop.type_operation = request.form.get('type_operation')
        prop.adresse = request.form.get('adresse')
        prop.ville = request.form.get('ville')
        prop.quartier = request.form.get('quartier')
        prop.prix = request.form.get('prix')
        prop.superficie = request.form.get('superficie') or None
        prop.nombre_chambres = request.form.get('nombre_chambres') or None
        prop.nombre_salles_bain = request.form.get('nombre_salles_bain') or None
        prop.nombre_garages = request.form.get('nombre_garages') or None
        prop.statut = request.form.get('statut')
        prop.devise = request.form.get('devise', 'EUR')
        
        # Mettre à jour les caractéristiques
        selected_caracs = request.form.getlist('caracteristiques')
        prop.caracteristiques = [] # Clear
        for c_id in selected_caracs:
            carac = db.session.get(Caracteristique, int(c_id))
            if carac:
                prop.caracteristiques.append(carac)
                
        try:
            log_activity(current_user.id, f"Modification propriété: {prop.reference_bien}", "proprietes", prop.id)
            db.session.commit()
            flash(f"La propriété {prop.reference_bien} a été mise à jour.", "success")
            return redirect(url_for('properties.view_property', property_id=prop.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"[PROPRIETES] Échec modification propriété id={property_id} par user_id={current_user.id}: {e}")
            logger.error(traceback.format_exc())
            flash("Erreur lors de la modification. Veuillez réessayer.", "danger")
            
    return render_template('properties/form.html', property=prop, proprietaires=proprietaires, caracteristiques=caracteristiques, action_title=f"Modifier {prop.reference_bien}")

@properties.route('/details/<int:property_id>')
@login_required
def view_property(property_id):
    prop = db.session.get(Propriete, property_id)
    if prop is None:
        abort(404)
    clients_list = db.session.execute(select(Client).order_by(Client.nom.asc())).scalars().all()
    agents_list = db.session.execute(select(Utilisateur).where(Utilisateur.actif == True).order_by(Utilisateur.nom.asc())).scalars().all()
    return render_template('properties/view.html', property=prop, clients=clients_list, agents=agents_list)

@properties.route('/supprimer/<int:property_id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def delete_property(property_id):
    prop = db.session.get(Propriete, property_id)
    if prop is None:
        abort(404)
    ref = prop.reference_bien
    
    # Supprimer les fichiers physiques associés (avec validation de chemin)
    static_dir = os.path.join(current_app.root_path, 'static')
    for photo in prop.photos:
        try:
            safe_path = safe_path_join(static_dir, photo.chemin_fichier)
            if safe_path and os.path.exists(safe_path):
                os.remove(safe_path)
        except Exception as e:
            current_app.logger.warning(f"Erreur suppression photo {photo.id}: {e}")
    for doc in prop.documents:
        try:
            safe_path = safe_path_join(static_dir, doc.chemin_fichier)
            if safe_path and os.path.exists(safe_path):
                os.remove(safe_path)
        except Exception as e:
            current_app.logger.warning(f"Erreur suppression document {doc.id}: {e}")
            
    try:
        db.session.delete(prop)
        log_activity(current_user.id, f"Suppression propriété: {ref}", "proprietes", property_id)
        db.session.commit()
        flash(f"La propriété {ref} a été supprimée.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[PROPRIETES] Échec suppression propriété id={property_id} par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la suppression. Veuillez réessayer.", "danger")
        
    return redirect(url_for('properties.list_properties'))

# --- Upload de Photos ---
@properties.route('/upload-photos/<int:property_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def upload_photos(property_id):
    prop = db.session.get(Propriete, property_id)
    if prop is None:
        abort(404)
    if 'photos' not in request.files:
        flash("Aucun fichier envoyé.", "warning")
        return redirect(url_for('properties.view_property', property_id=property_id))
        
    files = request.files.getlist('photos')
    upload_success = False
    max_size = current_app.config.get('MAX_FILE_SIZE_IMAGE', 10 * 1024 * 1024)
    
    for file in files:
        if not file or not file.filename:
            continue
        try:
            safe_path, rel_path, unique_name, file_size = validate_and_save_upload(
                file_storage=file,
                upload_subdir='uploads/photos',
                allowed_extensions=ALLOWED_IMAGES,
                max_size=max_size,
                category='image',
                validate_magic=True,
                user_id=current_user.id
            )
        except UploadValidationError as e:
            logger.warning(f"[UPLOAD] Photo rejetée : {e.message}")
            continue
        
        count = db.session.execute(select(sa_func.count(PhotoPropriete.id)).where(PhotoPropriete.propriete_id == property_id)).scalar()
        is_main = count == 0
        
        photo_entry = PhotoPropriete(
            propriete_id=property_id,
            chemin_fichier=rel_path,
            photo_principale=is_main
        )
        db.session.add(photo_entry)
        upload_success = True
            
    if upload_success:
        try:
            log_activity(current_user.id, f"Ajout photos pour {prop.reference_bien}", "photos_proprietes", prop.id)
            db.session.commit()
            flash("Les photos ont été téléversées avec succès.", "success")
        except Exception as e:
            db.session.rollback()
            logger.error(f"[PROPRIETES] Échec enregistrement photos pour propriété id={property_id}: {e}")
            logger.error(traceback.format_exc())
            flash("Erreur lors de l'enregistrement des photos en base.", "danger")
    else:
        flash("Aucune photo valide n'a été téléversée (formats autorisés: png, jpg, jpeg, webp, gif).", "danger")
        
    return redirect(url_for('properties.view_property', property_id=property_id))

@properties.route('/delete-photo/<int:photo_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def delete_photo(photo_id):
    photo = db.session.get(PhotoPropriete, photo_id)
    if photo is None:
        abort(404)
    property_id = photo.propriete_id
    
    # Supprimer le fichier (avec validation de chemin)
    static_dir = os.path.join(current_app.root_path, 'static')
    safe_path = safe_path_join(static_dir, photo.chemin_fichier)
    try:
        if safe_path and os.path.exists(safe_path):
            os.remove(safe_path)
    except Exception as e:
        current_app.logger.warning(f"Erreur suppression fichier photo {photo_id}: {e}")
        
    was_main = photo.photo_principale
    
    try:
        db.session.delete(photo)
        
        # Si la photo principale a été supprimée, désigner une nouvelle photo principale
        if was_main:
            next_photo = db.session.execute(select(PhotoPropriete).where(PhotoPropriete.propriete_id == property_id)).scalars().first()
            if next_photo:
                next_photo.photo_principale = True
                
        log_activity(current_user.id, "Suppression d'une photo", "photos_proprietes", photo_id)
        db.session.commit()
        flash("La photo a été supprimée.", "info")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[PROPRIETES] Échec suppression photo id={photo_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la suppression de la photo en base.", "danger")
        
    return redirect(url_for('properties.view_property', property_id=property_id))

@properties.route('/set-main-photo/<int:photo_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def set_main_photo(photo_id):
    photo = db.session.get(PhotoPropriete, photo_id)
    if photo is None:
        abort(404)
    property_id = photo.propriete_id
    
    # Retirer le statut principal de toutes les autres photos du bien
    stmt = update(PhotoPropriete).where(PhotoPropriete.propriete_id == property_id).values(photo_principale=False)
    db.session.execute(stmt)
    
    # Rendre cette photo principale
    photo.photo_principale = True
    
    try:
        log_activity(current_user.id, "Modification de la photo principale", "photos_proprietes", photo_id)
        db.session.commit()
        flash("La photo principale a été modifiée.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[PROPRIETES] Échec modification photo principale id={photo_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la modification de la photo principale.", "danger")
        
    return redirect(url_for('properties.view_property', property_id=property_id))

# --- Upload de Documents ---
@properties.route('/upload-document/<int:property_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def upload_document(property_id):
    prop = db.session.get(Propriete, property_id)
    if prop is None:
        abort(404)
    if 'document' not in request.files:
        flash("Aucun fichier envoyé.", "warning")
        return redirect(url_for('properties.view_property', property_id=property_id))
        
    file = request.files['document']
    nom_document = request.form.get('nom_document') or file.filename
    max_size = current_app.config.get('MAX_FILE_SIZE_DOCUMENT', 15 * 1024 * 1024)
    
    try:
        safe_path, rel_path, unique_name, file_size = validate_and_save_upload(
            file_storage=file,
            upload_subdir='uploads/documents',
            allowed_extensions=ALLOWED_DOCUMENTS,
            max_size=max_size,
            category='document',
            validate_magic=True,
            user_id=current_user.id
        )
    except UploadValidationError as e:
        flash(e.message, "danger")
        return redirect(url_for('properties.view_property', property_id=property_id))
    
    doc_entry = DocumentPropriete(
        propriete_id=property_id,
        nom_document=nom_document[:255],
        type_document=unique_name.rsplit('.', 1)[1].upper() if '.' in unique_name else 'UNKNOWN',
        chemin_fichier=rel_path
    )
    
    try:
        db.session.add(doc_entry)
        log_activity(current_user.id, f"Ajout document: {nom_document} pour {prop.reference_bien}", "documents_proprietes", prop.id)
        db.session.commit()
        flash(f"Le document '{nom_document}' a été téléversé avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        if os.path.exists(safe_path):
            os.remove(safe_path)
        logger.error(f"[PROPRIETES] Échec enregistrement document pour propriété id={property_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'enregistrement du document en base.", "danger")
        
    return redirect(url_for('properties.view_property', property_id=property_id))

@properties.route('/delete-document/<int:doc_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def delete_document(doc_id):
    doc = db.session.get(DocumentPropriete, doc_id)
    if doc is None:
        abort(404)
    property_id = doc.propriete_id
    
    # Supprimer le fichier physique (avec validation de chemin)
    static_dir = os.path.join(current_app.root_path, 'static')
    safe_path = safe_path_join(static_dir, doc.chemin_fichier)
    try:
        if safe_path and os.path.exists(safe_path):
            os.remove(safe_path)
    except Exception as e:
        current_app.logger.warning(f"Erreur suppression document {doc_id}: {e}")
        
    try:
        db.session.delete(doc)
        log_activity(current_user.id, f"Suppression document: {doc.nom_document}", "documents_proprietes", doc_id)
        db.session.commit()
        flash("Le document a été retiré.", "info")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[PROPRIETES] Échec suppression document id={doc_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la suppression du document.", "danger")
        
    return redirect(url_for('properties.view_property', property_id=property_id))

# --- Planification de Visite ---
@properties.route('/visite/ajouter/<int:property_id>', methods=['POST'])
@login_required
def add_visit(property_id):
    client_id = request.form.get('client_id')
    agent_id = request.form.get('agent_id')
    date_str = request.form.get('date_visite')
    time_str = request.form.get('heure_visite')
    compte_rendu = request.form.get('compte_rendu')
    
    try:
        date_visite = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        flash("Format de date ou heure invalide.", "danger")
        return redirect(url_for('properties.view_property', property_id=property_id))

    if date_visite < datetime.now():
        flash("La date de visite ne peut pas être dans le passé.", "danger")
        return redirect(url_for('properties.view_property', property_id=property_id))
        
    new_visit = Visite(
        client_id=client_id,
        propriete_id=property_id,
        agent_id=agent_id,
        date_visite=date_visite,
        compte_rendu=compte_rendu,
        statut='Planifiée'
    )
    
    try:
        db.session.add(new_visit)
        log_activity(current_user.id, f"Planification visite pour le bien {property_id}", "visites", new_visit.id)
        db.session.commit()
        flash("La visite a été planifiée avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[PROPRIETES] Échec planification visite pour propriété id={property_id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la planification de la visite.", "danger")
        
    return redirect(url_for('properties.view_property', property_id=property_id))

@properties.route('/exporter')
@login_required
def export_properties():
    try:
        properties_list = db.session.execute(select(Propriete).order_by(Propriete.date_ajout.desc())).scalars().all()
        excel_file = export_properties_to_excel(properties_list)
        log_activity(current_user.id, "Exportation Excel du catalogue immobilier", "proprietes")
        db.session.commit()
        return send_file(
            excel_file,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="Catalogue_Immobilier.xlsx"
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"[PROPRIETES] Échec export Excel par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'exportation. Veuillez réessayer.", "danger")
        return redirect(url_for('properties.list_properties'))

@properties.route('/importer', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def import_properties():
    if 'excel_file' not in request.files:
        flash("Aucun fichier envoyé.", "warning")
        return redirect(url_for('properties.list_properties'))
        
    file = request.files['excel_file']
    if not file or file.filename == '':
        flash("Fichier invalide.", "warning")
        return redirect(url_for('properties.list_properties'))

    if check_blocked_extension(file.filename):
        flash("Type de fichier non autorisé.", "danger")
        return redirect(url_for('properties.list_properties'))

    if not check_file_size_before_read(file, current_app.config.get('MAX_FILE_SIZE_EXCEL', 10 * 1024 * 1024)):
        flash("Le fichier Excel dépasse la taille maximale autorisée (10 Mo).", "danger")
        return redirect(url_for('properties.list_properties'))

    if not validate_excel_content(file.stream):
        flash("Le fichier ne semble pas être un fichier Excel valide.", "danger")
        return redirect(url_for('properties.list_properties'))
        
    try:
        properties_data = import_properties_from_excel(file)
        imported_count = 0
        
        for data in properties_data:
            count = db.session.execute(select(sa_func.count(Propriete.id))).scalar()
            reference_bien = f"BIEN-{datetime.now(timezone.utc).year}-{count + 1:04d}"
            
            new_prop = Propriete(
                reference_bien=reference_bien,
                titre=data["titre"],
                type_bien=data["type_bien"],
                type_operation=data["type_operation"],
                adresse=data["adresse"],
                ville=data["ville"],
                quartier=data["quartier"],
                prix=data["prix"],
                devise=data["devise"],
                superficie=data["superficie"],
                nombre_chambres=data["nombre_chambres"],
                nombre_salles_bain=data["nombre_salles_bain"],
                nombre_garages=data["nombre_garages"],
                statut=data["statut"],
                proprietaire_id=data["proprietaire_id"],
                description=data["description"]
            )
            db.session.add(new_prop)
            db.session.flush()
            imported_count += 1
            
        log_activity(current_user.id, f"Importation Excel catalogue : {imported_count} biens immobiliers créés", "proprietes")
        db.session.commit()
        flash(f"Importation réussie : {imported_count} biens immobiliers ajoutés au catalogue.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[PROPRIETES] Échec import Excel par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de l'importation. Vérifiez le format du fichier Excel.", "danger")
        
    return redirect(url_for('properties.list_properties'))
