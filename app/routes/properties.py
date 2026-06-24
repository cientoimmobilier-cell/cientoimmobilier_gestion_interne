from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, current_app, send_file
from flask_login import login_required, current_user
from app.models import (Propriete, Proprietaire, Caracteristique, PhotoPropriete, 
                        DocumentPropriete, Visite, Client, Utilisateur)
from app.utils.helpers import log_activity, role_required
from app import db
from datetime import datetime
from werkzeug.utils import secure_filename
import os
from app.services.excel_service import export_properties_to_excel, import_properties_from_excel

properties = Blueprint('properties', __name__)

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
ALLOWED_DOC_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

@properties.route('/')
@login_required
def list_properties():
    # Filtres
    search = request.args.get('search', '')
    type_bien = request.args.get('type_bien', '')
    statut = request.args.get('statut', '')
    prix_max = request.args.get('prix_max', '')
    
    query = Propriete.query
    
    if search:
        query = query.filter(
            (Propriete.reference_bien.ilike(f'%{search}%')) |
            (Propriete.titre.ilike(f'%{search}%')) |
            (Propriete.ville.ilike(f'%{search}%')) |
            (Propriete.quartier.ilike(f'%{search}%'))
        )
    if type_bien:
        query = query.filter_by(type_bien=type_bien)
    if statut:
        query = query.filter_by(statut=statut)
    if prix_max:
        try:
            query = query.filter(Propriete.prix <= float(prix_max))
        except ValueError:
            pass
            
    properties_list = query.order_by(Propriete.date_ajout.desc()).all()
    
    # Charger les types de biens pour le filtre
    property_types = ['Maison', 'Appartement', 'Terrain', 'Villa', 'Bureau', 'Local commercial', 'Entrepôt', 'Immeuble']
    
    return render_template(
        'properties/list.html', 
        properties=properties_list,
        property_types=property_types,
        search=search,
        type_bien=type_bien,
        statut=statut,
        prix_max=prix_max
    )

@properties.route('/ajouter', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier')
def add_property():
    proprietaires = Proprietaire.query.order_by(Proprietaire.nom.asc()).all()
    caracteristiques = Caracteristique.query.order_by(Caracteristique.nom.asc()).all()
    
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
        count = Propriete.query.count()
        reference_bien = f"BIEN-{datetime.utcnow().year}-{count + 1:04d}"
        
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
            carac = Caracteristique.query.get(int(c_id))
            if carac:
                new_prop.caracteristiques.append(carac)
                
        try:
            db.session.add(new_prop)
            db.session.commit()
            log_activity(current_user.id, f"Création propriété: {reference_bien}", "proprietes", new_prop.id)
            flash(f"La propriété {reference_bien} a été ajoutée avec succès.", "success")
            return redirect(url_for('properties.view_property', property_id=new_prop.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Erreur lors de la création: {e}", "danger")
            
    return render_template('properties/form.html', property=None, proprietaires=proprietaires, caracteristiques=caracteristiques, action_title="Ajouter une propriété")

@properties.route('/modifier/<int:property_id>', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier')
def edit_property(property_id):
    prop = Propriete.query.get_or_404(property_id)
    proprietaires = Proprietaire.query.order_by(Proprietaire.nom.asc()).all()
    caracteristiques = Caracteristique.query.order_by(Caracteristique.nom.asc()).all()
    
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
            carac = Caracteristique.query.get(int(c_id))
            if carac:
                prop.caracteristiques.append(carac)
                
        try:
            db.session.commit()
            log_activity(current_user.id, f"Modification propriété: {prop.reference_bien}", "proprietes", prop.id)
            flash(f"La propriété {prop.reference_bien} a été mise à jour.", "success")
            return redirect(url_for('properties.view_property', property_id=prop.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Erreur lors de la modification: {e}", "danger")
            
    return render_template('properties/form.html', property=prop, proprietaires=proprietaires, caracteristiques=caracteristiques, action_title=f"Modifier {prop.reference_bien}")

@properties.route('/details/<int:property_id>')
@login_required
def view_property(property_id):
    prop = Propriete.query.get_or_404(property_id)
    clients_list = Client.query.order_by(Client.nom.asc()).all()
    agents_list = Utilisateur.query.filter_by(actif=True).order_by(Utilisateur.nom.asc()).all()
    return render_template('properties/view.html', property=prop, clients=clients_list, agents=agents_list)

@properties.route('/supprimer/<int:property_id>', methods=['POST'])
@login_required
def delete_property(property_id):
    if current_user.role not in ['Administrateur', 'Directeur']:
        abort(403)
        
    prop = Propriete.query.get_or_404(property_id)
    ref = prop.reference_bien
    
    # Supprimer les fichiers physiques associés
    for photo in prop.photos:
        try:
            os.remove(os.path.join(current_app.root_path, 'static', photo.chemin_fichier))
        except:
            pass
    for doc in prop.documents:
        try:
            os.remove(os.path.join(current_app.root_path, 'static', doc.chemin_fichier))
        except:
            pass
            
    try:
        db.session.delete(prop)
        db.session.commit()
        log_activity(current_user.id, f"Suppression propriété: {ref}", "proprietes", property_id)
        flash(f"La propriété {ref} a été supprimée.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la suppression: {e}", "danger")
        
    return redirect(url_for('properties.list_properties'))

# --- Upload de Photos ---
@properties.route('/upload-photos/<int:property_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def upload_photos(property_id):
    prop = Propriete.query.get_or_404(property_id)
    if 'photos' not in request.files:
        flash("Aucun fichier envoyé.", "warning")
        return redirect(url_for('properties.view_property', property_id=property_id))
        
    files = request.files.getlist('photos')
    upload_success = False
    
    for file in files:
        if file and allowed_file(file.filename, ALLOWED_IMAGE_EXTENSIONS):
            filename = secure_filename(file.filename)
            unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'photos', unique_filename)
            
            file.save(filepath)
            
            # Sauvegarder le chemin relatif en base
            rel_path = f"uploads/photos/{unique_filename}"
            
            # S'il n'y a pas de photos existantes, celle-ci devient la photo principale
            is_main = PhotoPropriete.query.filter_by(propriete_id=property_id).count() == 0
            
            photo_entry = PhotoPropriete(
                propriete_id=property_id,
                chemin_fichier=rel_path,
                photo_principale=is_main
            )
            db.session.add(photo_entry)
            upload_success = True
            
    if upload_success:
        try:
            db.session.commit()
            log_activity(current_user.id, f"Ajout photos pour {prop.reference_bien}", "photos_proprietes", prop.id)
            flash("Les photos ont été téléversées avec succès.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Erreur lors de l'enregistrement en base: {e}", "danger")
    else:
        flash("Aucune photo valide n'a été téléversée (formats autorisés: png, jpg, jpeg, webp, gif).", "danger")
        
    return redirect(url_for('properties.view_property', property_id=property_id))

@properties.route('/delete-photo/<int:photo_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def delete_photo(photo_id):
    photo = PhotoPropriete.query.get_or_404(photo_id)
    property_id = photo.propriete_id
    
    # Supprimer le fichier
    filepath = os.path.join(current_app.root_path, 'static', photo.chemin_fichier)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print(f"Erreur suppression fichier: {e}")
        
    was_main = photo.photo_principale
    
    try:
        db.session.delete(photo)
        db.session.commit()
        
        # Si la photo principale a été supprimée, désigner une nouvelle photo principale
        if was_main:
            next_photo = PhotoPropriete.query.filter_by(propriete_id=property_id).first()
            if next_photo:
                next_photo.photo_principale = True
                db.session.commit()
                
        log_activity(current_user.id, "Suppression d'une photo", "photos_proprietes", photo_id)
        flash("La photo a été supprimée.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur de suppression en base: {e}", "danger")
        
    return redirect(url_for('properties.view_property', property_id=property_id))

@properties.route('/set-main-photo/<int:photo_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def set_main_photo(photo_id):
    photo = PhotoPropriete.query.get_or_404(photo_id)
    property_id = photo.propriete_id
    
    # Retirer le statut principal de toutes les autres photos du bien
    PhotoPropriete.query.filter_by(propriete_id=property_id).update({PhotoPropriete.photo_principale: False})
    
    # Rendre cette photo principale
    photo.photo_principale = True
    
    try:
        db.session.commit()
        log_activity(current_user.id, "Modification de la photo principale", "photos_proprietes", photo_id)
        flash("La photo principale a été modifiée.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la modification: {e}", "danger")
        
    return redirect(url_for('properties.view_property', property_id=property_id))

# --- Upload de Documents ---
@properties.route('/upload-document/<int:property_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def upload_document(property_id):
    prop = Propriete.query.get_or_404(property_id)
    if 'document' not in request.files:
        flash("Aucun fichier envoyé.", "warning")
        return redirect(url_for('properties.view_property', property_id=property_id))
        
    file = request.files['document']
    nom_document = request.form.get('nom_document') or file.filename
    
    if file and allowed_file(file.filename, ALLOWED_DOC_EXTENSIONS):
        filename = secure_filename(file.filename)
        unique_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{filename}"
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'documents', unique_filename)
        
        file.save(filepath)
        
        # Sauvegarder en base
        rel_path = f"uploads/documents/{unique_filename}"
        doc_entry = DocumentPropriete(
            propriete_id=property_id,
            nom_document=nom_document,
            type_document=filename.rsplit('.', 1)[1].upper(),
            chemin_fichier=rel_path
        )
        
        try:
            db.session.add(doc_entry)
            db.session.commit()
            log_activity(current_user.id, f"Ajout document: {nom_document} pour {prop.reference_bien}", "documents_proprietes", prop.id)
            flash(f"Le document '{nom_document}' a été téléversé avec succès.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Erreur d'enregistrement: {e}", "danger")
    else:
        flash("Ficher non autorisé ou invalide.", "danger")
        
    return redirect(url_for('properties.view_property', property_id=property_id))

@properties.route('/delete-document/<int:doc_id>', methods=['POST'])
@login_required
@role_required('Agent immobilier')
def delete_document(doc_id):
    doc = DocumentPropriete.query.get_or_404(doc_id)
    property_id = doc.propriete_id
    
    # Supprimer le fichier physique
    filepath = os.path.join(current_app.root_path, 'static', doc.chemin_fichier)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        print(f"Erreur suppression document: {e}")
        
    try:
        db.session.delete(doc)
        db.session.commit()
        log_activity(current_user.id, f"Suppression document: {doc.nom_document}", "documents_proprietes", doc_id)
        flash("Le document a été retiré.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur de suppression: {e}", "danger")
        
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
    except ValueError:
        flash("Format de date ou heure invalide.", "danger")
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
        db.session.commit()
        log_activity(current_user.id, f"Planification visite pour le bien {property_id}", "visites", new_visit.id)
        flash("La visite a été planifiée avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de la planification: {e}", "danger")
        
    return redirect(url_for('properties.view_property', property_id=property_id))

@properties.route('/exporter')
@login_required
def export_properties():
    properties_list = Propriete.query.order_by(Propriete.date_ajout.desc()).all()
    excel_file = export_properties_to_excel(properties_list)
    log_activity(current_user.id, "Exportation Excel du catalogue immobilier", "proprietes")
    return send_file(
        excel_file,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="Catalogue_Immobilier.xlsx"
    )

@properties.route('/importer', methods=['POST'])
@login_required
def import_properties():
    if current_user.role not in ['Administrateur', 'Directeur']:
        abort(403)
        
    if 'excel_file' not in request.files:
        flash("Aucun fichier envoyé.", "warning")
        return redirect(url_for('properties.list_properties'))
        
    file = request.files['excel_file']
    if not file or file.filename == '':
        flash("Fichier invalide.", "warning")
        return redirect(url_for('properties.list_properties'))
        
    try:
        properties_data = import_properties_from_excel(file)
        imported_count = 0
        
        for data in properties_data:
            count = Propriete.query.count()
            reference_bien = f"BIEN-{datetime.utcnow().year}-{count + 1:04d}"
            
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
            
        db.session.commit()
        log_activity(current_user.id, f"Importation Excel catalogue : {imported_count} biens immobiliers créés", "proprietes")
        flash(f"Importation réussie : {imported_count} biens immobiliers ajoutés au catalogue.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Erreur d'importation : {e}", "danger")
        
    return redirect(url_for('properties.list_properties'))
