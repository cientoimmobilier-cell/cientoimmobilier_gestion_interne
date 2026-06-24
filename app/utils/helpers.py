from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user
from app import db
from app.models import JournalActivite

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
