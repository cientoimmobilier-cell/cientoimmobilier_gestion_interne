import logging
import os
import re
import secrets
import string
from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user

from app import db
from app.models import JournalActivite

logger = logging.getLogger(__name__)

def generate_random_password(length=12):
    """Génère un mot de passe aléatoire sécurisé."""
    characters = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(secrets.choice(characters) for i in range(length))


_DANGEROUS_FORMULA_PREFIX = ('=', '+', '-', '@', '\t', '\r')


def neutralize_formula(value):
    """Prévient l'injection de formules dans les exports Excel/CSV.

    Préfixe d'une apostrophe les chaînes commençant par un caractère interprété
    par Excel/LibreOffice comme une formule, sans altérer les nombres négatifs
    légitimes (ex. -1500.50).
    """
    if not isinstance(value, str) or not value.startswith(_DANGEROUS_FORMULA_PREFIX):
        return value
    if value.startswith('-'):
        try:
            float(value)
            return value
        except ValueError:
            pass
    return "'" + value


def sanitize_search(search_term):
    """
    Échappe les caractères spéciaux LIKE (%, _) dans un terme de recherche
    pour éviter l'injection LIKE.
    """
    if not search_term:
        return ''
    search_term = search_term.replace('\\', '\\\\')
    search_term = search_term.replace('%', '\\%')
    search_term = search_term.replace('_', '\\_')
    return search_term.strip()


def sanitize_input(value, max_length=500):
    """
    Nettoie et valide un champ texte pour éviter l'injection de HTML
    ou de données corrompues.
    """
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    if len(value) > 200 and re.search(r'<[a-zA-Z]', value):
        return None
    return value[:max_length]


def safe_path_join(base_dir, untrusted_path):
    """
    Joint un chemin de base avec un chemin non fiable de manière sécurisée.
    Vérifie que le chemin résolu ne sort pas du répertoire de base.
    Retourne le chemin absolu sécurisé, ou None si le chemin est invalide.
    """
    full_path = os.path.realpath(os.path.join(base_dir, untrusted_path))
    base_real = os.path.realpath(base_dir)
    if not full_path.startswith(base_real + os.sep) and full_path != base_real:
        return None
    return full_path


def log_activity(user_id, action, table_concernee=None, enregistrement_id=None):
    """
    Enregistre une action utilisateur dans le journal d'activités.

    L'écriture est isolée dans un SAVEPOINT (begin_nested) : en cas d'échec,
    seule la ligne du journal est annulée. La transaction métier de l'appelant
    n'est JAMAIS remise à zéro (l'ancien code appelait db.session.rollback(),
    ce qui détruisait silencieusement l'opération en cours).
    """
    try:
        with db.session.begin_nested():
            log = JournalActivite(
                utilisateur_id=user_id,
                action=action,
                table_concernee=table_concernee,
                enregistrement_id=enregistrement_id
            )
            db.session.add(log)
    except Exception as e:
        logger.error(f"[JOURNAL] Échec enregistrement activité user_id={user_id}: {e}")


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
                flash('Vous n\'avez pas l\'autorisation d\'accéder à cette fonctionnalité.', 'danger')
                return redirect(url_for('dashboard.index'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator
