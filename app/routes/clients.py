from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, send_file, jsonify
from flask_login import login_required, current_user
from app.models import Client, DemandeClient
from app.utils.helpers import log_activity, sanitize_search, role_required
from app import db
from datetime import datetime, timezone
import time
import logging
import traceback
from app.services.excel_service import export_clients_to_excel, import_clients_from_excel

logger = logging.getLogger(__name__)

clients = Blueprint('clients', __name__)

@clients.route('/')
@login_required
def list_clients():
    search = request.args.get('search', '')
    if search:
        # Recherche par nom, prenom, email, telephone ou code_client
        safe_search = sanitize_search(search)
        like_pattern = f'%{safe_search}%'
        clients_list = Client.query.filter(
            (Client.nom.ilike(like_pattern)) |
            (Client.prenom.ilike(like_pattern)) |
            (Client.email.ilike(like_pattern)) |
            (Client.telephone.ilike(like_pattern)) |
            (Client.code_client.ilike(like_pattern))
        ).order_by(Client.nom.asc()).all()
    else:
        clients_list = Client.query.order_by(Client.nom.asc()).all()
        
    return render_template('clients/list.html', clients=clients_list, search=search)

@clients.route('/ajouter', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier', 'Assistant')
def add_client():
    if request.method == 'POST':
        nom = request.form.get('nom')
        prenom = request.form.get('prenom')
        telephone = request.form.get('telephone')
        telephone_secondaire = request.form.get('telephone_secondaire')
        email = request.form.get('email')
        adresse = request.form.get('adresse')
        ville = request.form.get('ville')
        profession = request.form.get('profession')
        zone_ciblee = request.form.get('zone_ciblee')
        description = request.form.get('description')
        budget_min = request.form.get('budget_min') or None
        budget_max = request.form.get('budget_max') or None
        devise = request.form.get('devise') or 'EUR'
        source_client = request.form.get('source_client')
        observations = request.form.get('observations')
        
        # --- Vérification des doublons ---
        doublon = None
        if telephone:
            doublon = Client.query.filter(Client.telephone == telephone).first()
            if doublon:
                flash(f"⚠️ Doublon détecté : le téléphone <strong>{telephone}</strong> est déjà enregistré pour "
                      f"<a href='{url_for('clients.view_client', client_id=doublon.id)}' class='alert-link'>"
                      f"{doublon.prenom} {doublon.nom}</a>.", "danger")
                return render_template('clients/form.html', client=None, action_title="Ajouter un client")
        if email:
            doublon = Client.query.filter(Client.email == email.lower()).first()
            if doublon:
                flash(f"⚠️ Doublon détecté : l'e-mail <strong>{email}</strong> est déjà enregistré pour "
                      f"<a href='{url_for('clients.view_client', client_id=doublon.id)}' class='alert-link'>"
                      f"{doublon.prenom} {doublon.nom}</a>.", "danger")
                return render_template('clients/form.html', client=None, action_title="Ajouter un client")

        # Génération du code client unique (timestamp + count pour éviter collision)
        count = Client.query.count()
        ts_suffix = str(int(time.time() * 1000))[-4:]
        code_client = f"CLI-{datetime.now(timezone.utc).year}-{count + 1:04d}-{ts_suffix}"
        
        # Validation des champs obligatoires
        if not nom or not nom.strip():
            flash("Le nom de famille est obligatoire.", "danger")
            return render_template('clients/form.html', client=None, action_title="Ajouter un client")
        if not prenom or not prenom.strip():
            flash("Le prénom est obligatoire.", "danger")
            return render_template('clients/form.html', client=None, action_title="Ajouter un client")

        new_client = Client(
            code_client=code_client,
            nom=nom.strip().upper(),       # Nom de famille toujours en majuscules
            prenom=prenom.strip().title(), # Prénom capitalisé
            telephone=telephone,
            telephone_secondaire=telephone_secondaire,
            email=email.strip().lower() if email else None,  # Email normalisé
            adresse=adresse,
            ville=ville,
            profession=profession,
            zone_ciblee=zone_ciblee,
            description=description,
            budget_min=budget_min,
            budget_max=budget_max,
            devise=devise,
            source_client=source_client,
            observations=observations
        )
        
        try:
            db.session.add(new_client)
            db.session.commit()
            log_activity(current_user.id, f"Création client: {new_client.prenom} {new_client.nom}", "clients", new_client.id)
            flash(f"Le client {new_client.prenom} {new_client.nom} a été créé avec succès (Code: {code_client}).", "success")
            return redirect(url_for('clients.view_client', client_id=new_client.id))
        except Exception as e:
            db.session.rollback()
            # Log complet de l'erreur côté serveur (visible dans les logs)
            logger.error(
                f"[CLIENTS] Échec création client '{nom} {prenom}' "
                f"par user_id={current_user.id} — {type(e).__name__}: {e}"
            )
            logger.error(traceback.format_exc())
            flash(
                f"Erreur lors de la création du client : {type(e).__name__}. "
                "Consultez les logs serveur pour les détails.",
                "danger"
            )

    return render_template('clients/form.html', client=None, action_title="Ajouter un client")

@clients.route('/modifier/<int:client_id>', methods=['GET', 'POST'])
@login_required
@role_required('Agent immobilier', 'Assistant')
def edit_client(client_id):
    client_obj = Client.query.get_or_404(client_id)
    
    if request.method == 'POST':
        new_telephone = request.form.get('telephone')
        new_email = request.form.get('email')

        # --- Vérification des doublons (exclure l'enregistrement courant) ---
        if new_telephone:
            doublon = Client.query.filter(Client.telephone == new_telephone, Client.id != client_id).first()
            if doublon:
                flash(f"⚠️ Doublon détecté : le téléphone <strong>{new_telephone}</strong> est déjà enregistré pour "
                      f"<a href='{url_for('clients.view_client', client_id=doublon.id)}' class='alert-link'>"
                      f"{doublon.prenom} {doublon.nom}</a>.", "danger")
                return render_template('clients/form.html', client=client_obj, action_title=f"Modifier {client_obj.prenom} {client_obj.nom}")
        if new_email:
            doublon = Client.query.filter(Client.email == new_email.lower(), Client.id != client_id).first()
            if doublon:
                flash(f"⚠️ Doublon détecté : l'e-mail <strong>{new_email}</strong> est déjà enregistré pour "
                      f"<a href='{url_for('clients.view_client', client_id=doublon.id)}' class='alert-link'>"
                      f"{doublon.prenom} {doublon.nom}</a>.", "danger")
                return render_template('clients/form.html', client=client_obj, action_title=f"Modifier {client_obj.prenom} {client_obj.nom}")

        nom_edit = request.form.get('nom', '').strip()
        prenom_edit = request.form.get('prenom', '').strip()
        if not nom_edit or not prenom_edit:
            flash("Le nom et le prénom sont obligatoires.", "danger")
            return render_template('clients/form.html', client=client_obj, action_title=f"Modifier {client_obj.prenom} {client_obj.nom}")
        client_obj.nom = nom_edit.upper()
        client_obj.prenom = prenom_edit.title()
        client_obj.telephone = new_telephone
        client_obj.telephone_secondaire = request.form.get('telephone_secondaire')
        client_obj.email = new_email.strip().lower() if new_email else None
        client_obj.adresse = request.form.get('adresse')
        client_obj.ville = request.form.get('ville')
        client_obj.profession = request.form.get('profession')
        client_obj.zone_ciblee = request.form.get('zone_ciblee')
        client_obj.description = request.form.get('description')
        client_obj.budget_min = request.form.get('budget_min') or None
        client_obj.budget_max = request.form.get('budget_max') or None
        client_obj.devise = request.form.get('devise') or 'EUR'
        client_obj.source_client = request.form.get('source_client')
        client_obj.observations = request.form.get('observations')
        
        try:
            db.session.commit()
            log_activity(current_user.id, f"Modification client: {client_obj.prenom} {client_obj.nom}", "clients", client_obj.id)
            flash(f"Les informations de {client_obj.prenom} {client_obj.nom} ont été mises à jour.", "success")
            return redirect(url_for('clients.view_client', client_id=client_obj.id))
        except Exception as e:
            db.session.rollback()
            logger.error(
                f"[CLIENTS] Échec modification client id={client_id} "
                f"par user_id={current_user.id} — {type(e).__name__}: {e}"
            )
            logger.error(traceback.format_exc())
            flash(f"Erreur lors de la modification : {type(e).__name__}. Consultez les logs.", "danger")
            
    return render_template('clients/form.html', client=client_obj, action_title=f"Modifier {client_obj.prenom} {client_obj.nom}")

@clients.route('/details/<int:client_id>')
@login_required
def view_client(client_id):
    client_obj = Client.query.get_or_404(client_id)
    return render_template('clients/view.html', client=client_obj)

@clients.route('/supprimer/<int:client_id>', methods=['POST'])
@login_required
def delete_client(client_id):
    # Restreint aux administrateurs ou directeurs
    if current_user.role not in ['Administrateur', 'Directeur']:
        abort(403)
        
    client_obj = Client.query.get_or_404(client_id)
    nom_complet = f"{client_obj.prenom} {client_obj.nom}"
    
    try:
        db.session.delete(client_obj)
        db.session.commit()
        log_activity(current_user.id, f"Suppression client: {nom_complet}", "clients", client_id)
        flash(f"Le client {nom_complet} a été supprimé.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(
            f"[CLIENTS] Échec suppression client id={client_id} "
            f"par user_id={current_user.id} — {type(e).__name__}: {e}"
        )
        logger.error(traceback.format_exc())
        flash(f"Impossible de supprimer ce client : {type(e).__name__}. Consultez les logs.", "danger")
        
    return redirect(url_for('clients.list_clients'))

@clients.route('/demande/ajouter/<int:client_id>', methods=['POST'])
@login_required
def add_demande(client_id):
    client_obj = Client.query.get_or_404(client_id)
    
    type_operation = request.form.get('type_operation')
    type_bien = request.form.get('type_bien')
    zone_recherche = request.form.get('zone_recherche')
    chambres = request.form.get('chambres') or None
    salles_bain = request.form.get('salles_bain') or None
    budget = request.form.get('budget') or None
    devise = request.form.get('devise') or 'EUR'
    etat_demande = request.form.get('etat_demande') or 'Pas urgence'
    
    new_demande = DemandeClient(
        client_id=client_id,
        type_operation=type_operation,
        type_bien=type_bien,
        zone_recherche=zone_recherche,
        chambres=chambres,
        salles_bain=salles_bain,
        budget=budget,
        devise=devise,
        etat_demande=etat_demande,
        statut='Recherche'
    )
    
    try:
        db.session.add(new_demande)
        db.session.commit()
        log_activity(current_user.id, f"Ajout critères de recherche pour {client_obj.prenom} {client_obj.nom}", "demandes_clients", new_demande.id)
        flash("Les critères de recherche ont été ajoutés pour ce client.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Erreur d'ajout de critères. Veuillez réessayer.", "danger")
        
    return redirect(url_for('clients.view_client', client_id=client_id))

@clients.route('/demande/supprimer/<int:demande_id>', methods=['POST'])
@login_required
def delete_demande(demande_id):
    demande = DemandeClient.query.get_or_404(demande_id)
    client_id = demande.client_id
    
    try:
        db.session.delete(demande)
        db.session.commit()
        log_activity(current_user.id, "Suppression de critères de recherche", "demandes_clients", demande_id)
        flash("Critères de recherche retirés.", "info")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de la suppression de critères. Veuillez réessayer.", "danger")
        
    return redirect(url_for('clients.view_client', client_id=client_id))

@clients.route('/verifier-doublon')
@login_required
def verifier_doublon_client():
    """Route AJAX — vérifie si un téléphone ou email est déjà utilisé par un autre client."""
    telephone = request.args.get('telephone', '').strip()
    email = request.args.get('email', '').strip().lower()
    exclude_id = request.args.get('exclude_id', type=int)  # ID de l'enregistrement en cours de modification

    if telephone:
        q = Client.query.filter(Client.telephone == telephone)
        if exclude_id:
            q = q.filter(Client.id != exclude_id)
        doublon = q.first()
        if doublon:
            return jsonify({
                'doublon': True,
                'champ': 'telephone',
                'nom': f"{doublon.prenom} {doublon.nom}",
                'url': url_for('clients.view_client', client_id=doublon.id)
            })

    if email:
        q = Client.query.filter(Client.email == email)
        if exclude_id:
            q = q.filter(Client.id != exclude_id)
        doublon = q.first()
        if doublon:
            return jsonify({
                'doublon': True,
                'champ': 'email',
                'nom': f"{doublon.prenom} {doublon.nom}",
                'url': url_for('clients.view_client', client_id=doublon.id)
            })

    return jsonify({'doublon': False})


@clients.route('/exporter')
@login_required
@role_required('Agent immobilier', 'Assistant')
def export_clients():
    clients_list = Client.query.order_by(Client.nom.asc()).all()
    excel_file = export_clients_to_excel(clients_list)
    log_activity(current_user.id, "Exportation Excel du portefeuille clients", "clients")
    return send_file(
        excel_file,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="Portefeuille_Clients.xlsx"
    )

@clients.route('/importer', methods=['POST'])
@login_required
def import_clients():
    if current_user.role not in ['Administrateur', 'Directeur']:
        abort(403)
        
    if 'excel_file' not in request.files:
        flash("Aucun fichier envoyé.", "warning")
        return redirect(url_for('clients.list_clients'))
        
    file = request.files['excel_file']
    if not file or file.filename == '':
        flash("Fichier invalide.", "warning")
        return redirect(url_for('clients.list_clients'))
        
    try:
        clients_data = import_clients_from_excel(file)
        imported_count = 0
        updated_count = 0
        
        for data in clients_data:
            existing = None
            if data["email"]:
                existing = Client.query.filter_by(email=data["email"]).first()
                
            if existing:
                existing.nom = data["nom"]
                existing.prenom = data["prenom"]
                existing.telephone = data["telephone"]
                existing.telephone_secondaire = data["telephone_secondaire"]
                existing.adresse = data["adresse"]
                existing.ville = data["ville"]
                existing.profession = data.get("profession")
                existing.zone_ciblee = data.get("zone_ciblee")
                existing.description = data.get("description")
                existing.budget_min = data.get("budget_min")
                existing.budget_max = data.get("budget_max")
                existing.devise = data.get("devise", "EUR")
                existing.source_client = data.get("source_client")
                existing.observations = data["observations"]
                updated_count += 1
            else:
                count = Client.query.count()
                code_client = f"CLI-{datetime.now(timezone.utc).year}-{count + 1:04d}"
                
                new_client = Client(
                    code_client=code_client,
                    nom=data["nom"],
                    prenom=data["prenom"],
                    telephone=data["telephone"],
                    telephone_secondaire=data["telephone_secondaire"],
                    email=data["email"],
                    adresse=data["adresse"],
                    ville=data.get("ville"),
                    profession=data.get("profession"),
                    zone_ciblee=data.get("zone_ciblee"),
                    description=data.get("description"),
                    budget_min=data.get("budget_min"),
                    budget_max=data.get("budget_max"),
                    devise=data.get("devise", "EUR"),
                    source_client=data.get("source_client"),
                    observations=data.get("observations")
                )
                db.session.add(new_client)
                db.session.flush()
                imported_count += 1
                
        db.session.commit()
        log_activity(current_user.id, f"Importation Excel clients : {imported_count} créés, {updated_count} mis à jour", "clients")
        flash(f"Importation réussie : {imported_count} clients créés, {updated_count} fiches mises à jour.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de l'importation. Vérifiez le format du fichier.", "danger")
        
    return redirect(url_for('clients.list_clients'))
