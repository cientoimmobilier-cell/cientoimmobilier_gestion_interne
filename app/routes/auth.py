from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.models import Utilisateur
from app.utils.helpers import log_activity
from app import db
from datetime import datetime, timedelta
from collections import defaultdict
from urllib.parse import urlparse

auth = Blueprint('auth', __name__)

# Rate limiting en mémoire : {ip: {'count': int, 'first_attempt': datetime}}
_login_attempts = defaultdict(lambda: {'count': 0, 'first_attempt': None})
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=5)

def _is_rate_limited(ip):
    """Vérifie si l'IP est bloquée suite à trop de tentatives échouées."""
    record = _login_attempts[ip]
    if record['count'] >= MAX_LOGIN_ATTEMPTS and record['first_attempt']:
        elapsed = datetime.now() - record['first_attempt']
        if elapsed < LOCKOUT_DURATION:
            remaining = (LOCKOUT_DURATION - elapsed).seconds // 60 + 1
            return True, remaining
        else:
            # Réinitialiser après expiration du blocage
            _login_attempts[ip] = {'count': 0, 'first_attempt': None}
    return False, 0

def _record_failed_attempt(ip):
    """Enregistre une tentative échouée."""
    record = _login_attempts[ip]
    if record['count'] == 0:
        record['first_attempt'] = datetime.now()
    record['count'] += 1

def _reset_attempts(ip):
    """Réinitialise le compteur après une connexion réussie."""
    _login_attempts[ip] = {'count': 0, 'first_attempt': None}

def _is_safe_redirect_url(target):
    """Vérifie qu'une URL de redirection est sûre (interne uniquement)."""
    if not target:
        return False
    parsed = urlparse(target)
    # N'autoriser que les URLs relatives (pas de scheme ni de netloc)
    return parsed.scheme == '' and parsed.netloc == '' and target.startswith('/')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        client_ip = request.remote_addr
        
        # Vérifier le rate limiting
        is_blocked, minutes_left = _is_rate_limited(client_ip)
        if is_blocked:
            flash(f'Trop de tentatives échouées. Réessayez dans {minutes_left} minute(s).', 'danger')
            log_activity(None, f"Tentative de connexion bloquée (rate limit) depuis {client_ip}")
            return redirect(url_for('auth.login'))
        
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        user = Utilisateur.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            _record_failed_attempt(client_ip)
            attempts_left = MAX_LOGIN_ATTEMPTS - _login_attempts[client_ip]['count']
            if attempts_left > 0:
                flash(f'Adresse email ou mot de passe incorrect. {attempts_left} tentative(s) restante(s).', 'danger')
            else:
                flash(f'Compte temporairement bloqué. Réessayez dans {LOCKOUT_DURATION.seconds // 60} minutes.', 'danger')
            log_activity(None, f"Tentative de connexion échouée pour '{email}' depuis {client_ip}")
            return redirect(url_for('auth.login'))
            
        if not user.actif:
            flash('Ce compte a été désactivé. Contactez l\'administrateur.', 'warning')
            return redirect(url_for('auth.login'))
        
        # Connexion réussie — réinitialiser les tentatives
        _reset_attempts(client_ip)
        login_user(user, remember=remember)
        log_activity(user.id, "Connexion réussie")
        
        # Validation de l'URL de redirection (Fix #1 — Open Redirect)
        next_page = request.args.get('next')
        if next_page and _is_safe_redirect_url(next_page):
            return redirect(next_page)
        return redirect(url_for('dashboard.index'))
        
    return render_template('auth/login.html')

@auth.route('/logout')
@login_required
def logout():
    user_id = current_user.id
    logout_user()
    log_activity(user_id, "Déconnexion")
    flash('Vous avez été déconnecté.', 'success')
    return redirect(url_for('auth.login'))

@auth.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Vérifier l'ancien mot de passe
        if not current_user.check_password(current_password):
            flash("L'ancien mot de passe est incorrect.", "danger")
            return redirect(url_for('auth.change_password'))
        
        # Vérifier la correspondance
        if new_password != confirm_password:
            flash("Les nouveaux mots de passe ne correspondent pas.", "danger")
            return redirect(url_for('auth.change_password'))
        
        # Vérifier la longueur minimale
        if len(new_password) < 8:
            flash("Le nouveau mot de passe doit contenir au moins 8 caractères.", "danger")
            return redirect(url_for('auth.change_password'))
        
        try:
            current_user.set_password(new_password)
            db.session.commit()
            log_activity(current_user.id, "Changement de mot de passe")
            flash("Votre mot de passe a été modifié avec succès.", "success")
            return redirect(url_for('dashboard.index'))
        except Exception as e:
            db.session.rollback()
            flash(f"Erreur lors du changement de mot de passe : {e}", "danger")
    
    return render_template('auth/change_password.html')
