from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user
from app import db
from app.models import JournalActivite
import re
import os


def sanitize_search(search_term):
    """
    Échappe les caractères spéciaux LIKE (%, _) dans un terme de recherche
    pour éviter l'injection LIKE (Fix #2).
    """
    if not search_term:
        return ''
    # Échapper les caractères spéciaux SQL LIKE
    search_term = search_term.replace('\\', '\\\\')
    search_term = search_term.replace('%', '\\%')
    search_term = search_term.replace('_', '\\_')
    return search_term.strip()


def sanitize_input(value, max_length=500):
    """
    Nettoie et valide un champ texte pour éviter l'injection de HTML
    ou de données corrompues (Fix #12).
    """
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    # Rejeter tout contenu ressemblant à du HTML (> 200 chars avec balises)
    if len(value) > 200 and re.search(r'<[a-zA-Z]', value):
        return None
    # Tronquer si trop long
    return value[:max_length]


def safe_path_join(base_dir, untrusted_path):
    """
    Joint un chemin de base avec un chemin non fiable de manière sécurisée.
    Vérifie que le chemin résolu ne sort pas du répertoire de base (Fix #5).
    Retourne le chemin absolu sécurisé, ou None si le chemin est invalide.
    """
    # Normaliser et résoudre le chemin complet
    full_path = os.path.realpath(os.path.join(base_dir, untrusted_path))
    base_real = os.path.realpath(base_dir)
    
    # Vérifier que le chemin résolu est bien un sous-chemin du répertoire de base
    if not full_path.startswith(base_real + os.sep) and full_path != base_real:
        return None
    return full_path

def log_activity(user_id, action, table_concernee=None, enregistrement_id=None):
    """
    Enregistre une action utilisateur dans le journal d'activités.
    """
    try:
        log = JournalActivite(
            utilisateur_id=user_id,
            action=action,
            table_concernee=table_concernee,
            enregistrement_id=enregistrement_id
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # En production, on logguerait l'erreur
        print(f"Erreur lors de l'enregistrement de l'activité: {e}")

def role_required(*roles):
    """
    Décorateur pour vérifier si l'utilisateur courant possède l'un des rôles autorisés.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            # Les Administrateurs et Directeurs ont accès à tout par défaut
            allowed_roles = set(roles)
            allowed_roles.update(['Administrateur', 'Directeur'])
            
            if current_user.role not in allowed_roles:
                flash("Vous n'avez pas l'autorisation d'accéder à cette fonctionnalité.", "danger")
                return redirect(url_for('dashboard.index'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator
