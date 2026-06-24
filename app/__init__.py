import os
from flask import Flask
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

    # En-têtes HTTP de sécurité
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response
            
    return app
