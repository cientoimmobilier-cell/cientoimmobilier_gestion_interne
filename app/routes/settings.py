import logging
import traceback
from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from app.models import Utilisateur, Transaction, Visite, Commission, BienAirbnb, MouvementFinancier
from app.utils.helpers import log_activity, role_required
from app import db
from sqlalchemy import select, func as sa_func

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/users')
@login_required
@role_required('Administrateur', 'Directeur')
def list_users():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'nom')
    order = request.args.get('order', 'asc')

    stmt = select(Utilisateur)

    if search:
        search_term = f'%{search}%'
        stmt = stmt.where(
            db.or_(Utilisateur.nom.ilike(search_term), Utilisateur.prenom.ilike(search_term), Utilisateur.email.ilike(search_term))
        )

    sort_column = getattr(Utilisateur, sort, Utilisateur.nom)
    try:
        stmt = stmt.order_by(sort_column.asc() if order == 'asc' else sort_column.desc())
    except:
        stmt = stmt.order_by(Utilisateur.nom.asc())

    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    return render_template('settings/users_list.html', pagination=pagination, sort=sort, order=order)

@settings_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def add_user():
    if request.method == 'POST':
        nom = request.form.get('nom')
        prenom = request.form.get('prenom')
        email = request.form.get('email')
        telephone = request.form.get('telephone')
        role = request.form.get('role')
        zone_affectation = request.form.get('zone_affectation')
        
        # Check if email exists
        if db.session.execute(select(Utilisateur).where(Utilisateur.email == email)).scalars().first():
            flash('Cet email est déjà utilisé par un autre utilisateur.', 'danger')
            return redirect(url_for('settings.add_user'))
            
        password = request.form.get('password', '').strip()

        # ── Validations du mot de passe AVANT le hachage ──────────────────────
        # IMPORTANT : set_password() déclenche bcrypt (coûteux). On valide
        # systématiquement avant pour ne jamais hasher un mot de passe invalide.
        if not password:
            flash('Le mot de passe est obligatoire.', 'danger')
            return redirect(url_for('settings.add_user'))
        if len(password) < 8:
            flash('Le mot de passe doit contenir au moins 8 caractères.', 'danger')
            return redirect(url_for('settings.add_user'))

        # Validations passées — on peut maintenant créer l'objet et hacher le MDP
        user = Utilisateur(
            nom=nom,
            prenom=prenom,
            email=email,
            telephone=telephone,
            role=role,
            zone_affectation=zone_affectation if role == 'Agent immobilier' else None
        )
        user.set_password(password)  # Hash bcrypt uniquement si validations OK
        
        try:
            db.session.add(user)
            log_activity(current_user.id, 'Création', 'utilisateurs', user.id)
            db.session.commit()
            flash(f'Utilisateur créé avec succès.', 'success')
            return redirect(url_for('settings.list_users'))
        except Exception:
            db.session.rollback()
            logger.error(f"[SETTINGS] Échec création utilisateur par user_id={current_user.id}")
            logger.error(traceback.format_exc())
            flash('Erreur lors de la création de l\'utilisateur. Veuillez réessayer.', 'danger')
            return redirect(url_for('settings.add_user'))
        
    return render_template('settings/user_form.html', action="add")

@settings_bp.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def edit_user(id):
    user = db.session.get(Utilisateur, id)
    if user is None:
        abort(404)
    
    if request.method == 'POST':
        user.nom = request.form.get('nom')
        user.prenom = request.form.get('prenom')
        
        new_email = request.form.get('email')
        if new_email != user.email and db.session.execute(select(Utilisateur).where(Utilisateur.email == new_email)).scalars().first():
            flash('Cet email est déjà utilisé.', 'danger')
            return redirect(url_for('settings.edit_user', id=user.id))
            
        user.email = new_email
        user.telephone = request.form.get('telephone')
        user.role = request.form.get('role')
        user.zone_affectation = request.form.get('zone_affectation') if user.role == 'Agent immobilier' else None
        user.actif = 'actif' in request.form
        
        try:
            log_activity(current_user.id, 'Modification', 'utilisateurs', user.id)
            db.session.commit()
            flash('Utilisateur modifié avec succès.', 'success')
            return redirect(url_for('settings.list_users'))
        except Exception:
            db.session.rollback()
            logger.error(f"[SETTINGS] Échec modification utilisateur id={id} par user_id={current_user.id}")
            logger.error(traceback.format_exc())
            flash('Erreur lors de la modification. Veuillez réessayer.', 'danger')
        
    return render_template('settings/user_form.html', action="edit", user=user)

@settings_bp.route('/users/delete/<int:id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def delete_user(id):
    if current_user.id == id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "danger")
        return redirect(url_for('settings.list_users'))
        
    user = db.session.get(Utilisateur, id)
    if user is None:
        abort(404)
    nom_complet = f"{user.prenom} {user.nom}"
    
    # Vérifier les dépendances avant suppression
    dependances = []
    tx_count = db.session.execute(select(sa_func.count(Transaction.id)).where(Transaction.agent_id == id)).scalar()
    if tx_count:
        dependances.append(f"{tx_count} transaction(s)")
    commission_count = db.session.execute(select(sa_func.count(Commission.id)).where(Commission.agent_id == id)).scalar()
    if commission_count:
        dependances.append(f"{commission_count} commission(s)")
    visite_count = db.session.execute(select(sa_func.count(Visite.id)).where(Visite.agent_id == id)).scalar()
    if visite_count:
        dependances.append(f"{visite_count} visite(s)")
    airbnb_count = db.session.execute(select(sa_func.count(BienAirbnb.id)).where(BienAirbnb.agent_id == id)).scalar()
    if airbnb_count:
        dependances.append(f"{airbnb_count} bien(s) AirBNB")
    mvt_count = db.session.execute(select(sa_func.count(MouvementFinancier.id)).where(MouvementFinancier.utilisateur_id == id)).scalar()
    if mvt_count:
        dependances.append(f"{mvt_count} mouvement(s) financier(s)")
    
    if dependances:
        flash(
            f"Impossible de supprimer {nom_complet} : {', '.join(dependances)} lui sont encore rattachées. "
            f"Réaffectez ou supprimez d'abord ces éléments.",
            "danger"
        )
        return redirect(url_for('settings.list_users'))
    
    try:
        db.session.delete(user)
        log_activity(current_user.id, 'Suppression', 'utilisateurs', id)
        db.session.commit()
        flash(f"L'utilisateur {nom_complet} a été supprimé avec succès.", "success")
    except Exception:
        db.session.rollback()
        logger.error(f"[SETTINGS] Échec suppression utilisateur id={id} par user_id={current_user.id}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la suppression de l'utilisateur.", "danger")
        
    return redirect(url_for('settings.list_users'))

@settings_bp.route('/users/reset-password/<int:id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def reset_user_password(id):
    """Réinitialiser le mot de passe d'un utilisateur."""
    if current_user.id == id:
        flash("Utilisez la page 'Changer le mot de passe' pour modifier votre propre mot de passe.", "info")
        return redirect(url_for('settings.list_users'))
    
    user = db.session.get(Utilisateur, id)
    if user is None:
        abort(404)
    new_password = request.form.get('new_password', '').strip()

    # ── Validations AVANT le hachage ──────────────────────────────────────────
    if not new_password:
        flash("Veuillez saisir un nouveau mot de passe.", "danger")
        return redirect(url_for('settings.list_users'))
    if len(new_password) < 8:
        flash("Le nouveau mot de passe doit contenir au moins 8 caractères.", "danger")
        return redirect(url_for('settings.list_users'))

    # Validations passées — hachage sécurisé
    user.set_password(new_password)
    
    try:
        log_activity(current_user.id, f"Réinitialisation mot de passe de {user.prenom} {user.nom}", "utilisateurs", user.id)
        db.session.commit()
        flash(f"Le mot de passe de {user.prenom} {user.nom} a été mis à jour avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[SETTINGS] Échec réinitialisation mot de passe user id={id} par user_id={current_user.id}: {e}")
        logger.error(traceback.format_exc())
        flash("Erreur lors de la réinitialisation du mot de passe. Veuillez réessayer.", "danger")
    
    return redirect(url_for('settings.list_users'))
