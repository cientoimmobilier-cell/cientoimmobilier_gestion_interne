from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import Utilisateur
from app.utils import log_activity, role_required
from app import db
import string
import random

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

def generate_random_password(length=12):
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choice(characters) for i in range(length))

@settings_bp.route('/users')
@login_required
@role_required('Administrateur', 'Directeur')
def list_users():
    users = Utilisateur.query.all()
    return render_template('settings/users_list.html', users=users)

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
        if Utilisateur.query.filter_by(email=email).first():
            flash('Cet email est déjà utilisé par un autre utilisateur.', 'danger')
            return redirect(url_for('settings.add_user'))
            
        password = generate_random_password()
        
        user = Utilisateur(
            nom=nom,
            prenom=prenom,
            email=email,
            telephone=telephone,
            role=role,
            zone_affectation=zone_affectation if role == 'Agent immobilier' else None
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        log_activity(current_user.id, 'Création', 'utilisateurs', user.id)
        flash(f'Utilisateur créé avec succès. Mot de passe généré : {password} (À transmettre à l\'utilisateur)', 'success')
        return redirect(url_for('settings.list_users'))
        
    return render_template('settings/user_form.html', action="add")

@settings_bp.route('/users/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def edit_user(id):
    user = Utilisateur.query.get_or_404(id)
    
    if request.method == 'POST':
        user.nom = request.form.get('nom')
        user.prenom = request.form.get('prenom')
        
        new_email = request.form.get('email')
        if new_email != user.email and Utilisateur.query.filter_by(email=new_email).first():
            flash('Cet email est déjà utilisé.', 'danger')
            return redirect(url_for('settings.edit_user', id=user.id))
            
        user.email = new_email
        user.telephone = request.form.get('telephone')
        user.role = request.form.get('role')
        user.zone_affectation = request.form.get('zone_affectation') if user.role == 'Agent immobilier' else None
        user.actif = 'actif' in request.form
        
        db.session.commit()
        log_activity(current_user.id, 'Modification', 'utilisateurs', user.id)
        flash('Utilisateur modifié avec succès.', 'success')
        return redirect(url_for('settings.list_users'))
        
    return render_template('settings/user_form.html', action="edit", user=user)

@settings_bp.route('/users/delete/<int:id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def delete_user(id):
    if current_user.id == id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "danger")
        return redirect(url_for('settings.list_users'))
        
    user = Utilisateur.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    
    log_activity(current_user.id, 'Suppression', 'utilisateurs', id)
    flash('Utilisateur supprimé avec succès.', 'success')
    return redirect(url_for('settings.list_users'))
