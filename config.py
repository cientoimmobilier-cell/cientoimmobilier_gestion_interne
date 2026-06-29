import os
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()
    
    # Vérifier que le SECRET_KEY est suffisamment fort
    if len(SECRET_KEY) < 32:
        import warnings
        warnings.warn("SECRET_KEY trop court ! Utilisez au moins 32 caractères.", stacklevel=2)
    
    # Construction de l'URI PostgreSQL à partir des variables d'environnement
    db_user = os.environ.get('DB_USER', 'postgres')
    db_password = os.environ.get('DB_PASSWORD', 'postgres')
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_port = os.environ.get('DB_PORT', '5432')
    db_name = os.environ.get('DB_NAME', 'ciento_immobilier')
    
    # Render fournit l'URL complète via DATABASE_URL
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = database_url
    else:
        SQLALCHEMY_DATABASE_URI = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Dossier d'upload pour les images et documents
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(basedir, 'app', 'static', 'uploads')
    
    # Taille maximale des fichiers (16 Mo par défaut)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    
    # Sécurité des sessions
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 heure
    
    # Sécurité du cookie "Remember Me"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    
    # Protection CSRF — durée de validité du token (1 heure)
    WTF_CSRF_TIME_LIMIT = 3600
    
    # Mode debug configurable
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')
    
    # SESSION_COOKIE_SECURE activé seulement hors debug (nécessite HTTPS)
    SESSION_COOKIE_SECURE = not DEBUG
    REMEMBER_COOKIE_SECURE = not DEBUG
