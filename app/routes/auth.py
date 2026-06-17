from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models import Utilisateur
from app.utils import log_activity
from app import db

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = Utilisateur.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            flash('Adresse email ou mot de passe incorrect.', 'danger')
            return redirect(url_for('auth.login'))
            
        if not user.actif:
            flash('Ce compte a été désactivé. Contactez l\'administrateur.', 'warning')
            return redirect(url_for('auth.login'))
            
        login_user(user, remember=remember)
        log_activity(user.id, "Connexion réussie")
        
        next_page = request.args.get('next')
        return redirect(next_page or url_for('dashboard.index'))
        
    return render_template('auth/login.html')

@auth.route('/logout')
@login_required
def logout():
    user_id = current_user.id
    logout_user()
    log_activity(user_id, "Déconnexion")
    flash('Vous avez été déconnecté.', 'success')
    return redirect(url_for('auth.login'))
