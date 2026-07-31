import os
import logging
from flask import Flask, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect

# Initialisation des extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
csrf = CSRFProtect()
login_manager.login_view = 'auth.login'
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "warning"

def create_app(config_class=None):
    from config import Config
    app = Flask(__name__)
    app.config.from_object(config_class or Config)

    # ── Configuration du logging Python ─────────────────────────────────────
    # Format : timestamp | niveau | module | message
    log_level = logging.DEBUG if app.config.get('DEBUG') else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.StreamHandler()]
    )
    # Réduire le bruit des bibliothèques tierces en production
    if not app.config.get('DEBUG'):
        logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    # Initialisation des extensions avec l'application
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Assurer la création du dossier d'upload
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'photos'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'documents'), exist_ok=True)
    
    # Enregistrement des Blueprints
    from app.routes.auth import auth as auth_blueprint
    from app.routes.dashboard import dashboard as dashboard_blueprint
    from app.routes.clients import clients as clients_blueprint
    from app.routes.owners import owners as owners_blueprint
    from app.routes.properties import properties as properties_blueprint
    from app.routes.transactions import transactions as transactions_blueprint
    from app.routes.settings import settings_bp
    from app.routes.airbnb import airbnb as airbnb_blueprint
    from app.routes.agents import agents as agents_blueprint
    from app.routes.finance import finance as finance_blueprint
    from app.routes.partenaires import partenaires as partenaires_blueprint
    from app.routes.occupation import occupation as occupation_blueprint
    from app.routes.cloud_backup import cloud_backup_bp
    
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(dashboard_blueprint, url_prefix='/')
    app.register_blueprint(clients_blueprint, url_prefix='/clients')
    app.register_blueprint(owners_blueprint, url_prefix='/proprietaires')
    app.register_blueprint(properties_blueprint, url_prefix='/proprietes')
    app.register_blueprint(transactions_blueprint, url_prefix='/transactions')
    app.register_blueprint(settings_bp)
    app.register_blueprint(airbnb_blueprint, url_prefix='/airbnb')
    app.register_blueprint(agents_blueprint, url_prefix='/agents')
    app.register_blueprint(finance_blueprint, url_prefix='/finance')
    app.register_blueprint(partenaires_blueprint, url_prefix='/partenaires')
    app.register_blueprint(occupation_blueprint, url_prefix='/occupations')
    app.register_blueprint(cloud_backup_bp)

    # Planificateur des sauvegardes cloud (une seule instance par processus)
    if not app.config.get('TESTING'):
        from app.services.scheduler_service import BackupScheduler
        scheduler = app.extensions.get('backup_scheduler')
        if scheduler is None:
            scheduler = BackupScheduler()
            app.extensions['backup_scheduler'] = scheduler
        scheduler.start(app)
    
    # Contexte global pour les templates (rôles et utilitaires)
    @app.context_processor
    def inject_roles():
        return dict(
            ROLES={
                'ADMIN': 'Administrateur',
                'DIRECTEUR': 'Directeur',
                'AGENT': 'Agent immobilier',
                'ASSISTANT': 'Assistant',
                'COMPTABLE': 'Comptable'
            }
        )
    
    @app.template_filter('format_price')
    def format_price_filter(price, currency='EUR'):
        if price is None:
            return '--'
        try:
            formatted = "{:,.2f}".format(float(price)).replace(',', ' ')
            if formatted.endswith('.00'):
                formatted = formatted[:-3]
        except (ValueError, TypeError):
            return price
            
        if currency == 'USD':
            return f"${formatted}"
        elif currency == 'HTG':
            return f"{formatted} HTG"
        else:
            return f"{formatted} €"

    # Injecter le nonce CSP dans tous les templates
    @app.context_processor
    def inject_csp_nonce():
        from app.utils.security import generate_nonce
        return dict(csp_nonce=generate_nonce)

    # En-têtes HTTP de sécurité (CSP, HSTS, etc.)
    @app.after_request
    def set_security_headers(response):
        from app.utils.security import build_csp, SECURITY_HEADERS
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        response.headers['Content-Security-Policy'] = build_csp()
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    # Gestionnaires d'erreurs — ne jamais divulguer les détails internes
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template_string('''
            {% extends "base.html" %}
            {% block title %}Accès refusé{% endblock %}
            {% block header_title %}Accès refusé{% endblock %}
            {% block content %}
            <div class="text-center py-5">
                <i class="fa-solid fa-lock fa-3x text-warning mb-3"></i>
                <h3>Accès refusé</h3>
                <p class="text-muted">Vous n'avez pas l'autorisation d'accéder à cette page.</p>
                <a href="{{ url_for('dashboard.index') }}" class="btn btn-accent rounded-3 mt-3">Retour au tableau de bord</a>
            </div>
            {% endblock %}
        '''), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template_string('''
            {% extends "base.html" %}
            {% block title %}Page introuvable{% endblock %}
            {% block header_title %}Page introuvable{% endblock %}
            {% block content %}
            <div class="text-center py-5">
                <i class="fa-solid fa-map-signs fa-3x text-muted mb-3"></i>
                <h3>Page introuvable</h3>
                <p class="text-muted">La page demandée n'existe pas.</p>
                <a href="{{ url_for('dashboard.index') }}" class="btn btn-accent rounded-3 mt-3">Retour au tableau de bord</a>
            </div>
            {% endblock %}
        '''), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template_string('''
            {% extends "base.html" %}
            {% block title %}Erreur serveur{% endblock %}
            {% block header_title %}Erreur serveur{% endblock %}
            {% block content %}
            <div class="text-center py-5">
                <i class="fa-solid fa-triangle-exclamation fa-3x text-danger mb-3"></i>
                <h3>Erreur interne du serveur</h3>
                <p class="text-muted">Une erreur inattendue s'est produite. L'administrateur a été notifié.</p>
                <a href="{{ url_for('dashboard.index') }}" class="btn btn-accent rounded-3 mt-3">Retour au tableau de bord</a>
            </div>
            {% endblock %}
        '''), 500
        
    @app.route('/health')
    def health_check():
        """
        Endpoint de healthcheck — retourne uniquement 'OK'.
        NOTE : L'initialisation de la base de données doit être réalisée
        exclusivement via la commande : python init_db.py
        La route /setup-database a été supprimée car elle constituait une
        vulnérabilité critique (création de compte admin sans authentification).
        """
        return "OK", 200

    return app
