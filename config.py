import os
import sys
from urllib.parse import quote, quote_plus

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# En mode PyInstaller onefile, ``__file__`` pointe vers _MEIPASS (dossier
# temporaire d'extraction, supprimé à la fermeture). Le .env et les données
# utilisateur doivent donc être lus depuis le dossier du .exe, jamais _MEIPASS.
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)

load_dotenv(os.path.join(BASE_DIR, '.env'))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', '')

    _PLACEHOLDER_KEY = 'change-me-to-a-random-secret-key-at-least-32-chars'
    if (not SECRET_KEY or len(SECRET_KEY) < 32
            or SECRET_KEY == _PLACEHOLDER_KEY):
        raise RuntimeError(
            'SECRET_KEY manquante, trop courte ou encore celle du modèle '
            '(.env.example). Définissez la variable d\'environnement SECRET_KEY '
            '(au moins 32 caractères). Aucune génération automatique : celle-ci '
            'invalidait les sessions à chaque redémarrage. Génération : '
            'python -c "import secrets; print(secrets.token_hex(32))"')

    db_user = os.environ.get('DB_USER', 'postgres')
    db_password = os.environ.get('DB_PASSWORD', 'postgres')
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_port = os.environ.get('DB_PORT', '5432')
    db_name = os.environ.get('DB_NAME', 'ciento_immobilier')

    # Application 100 % locale (desktop Windows) : PostgreSQL local uniquement,
    # plus aucune URL de base de données cloud (DATABASE_URL / POSTGRES_URL de
    # Render/Vercel ont été retirées).
    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{quote_plus(db_user)}:{quote_plus(db_password)}"
        f"@{db_host}:{db_port}/{quote(db_name, safe='')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Chemin absolu, indépendant du répertoire courant. En mode frozen,
    # BASE_DIR est le dossier du .exe : les uploads ne doivent jamais atterrir
    # dans le dossier temp _MEIPASS (ils seraient perdus à la fermeture).
    _upload = (os.environ.get('UPLOAD_FOLDER')
               or os.path.join(BASE_DIR, 'app', 'static', 'uploads'))
    if not os.path.isabs(_upload):
        _upload = os.path.join(BASE_DIR, _upload)
    UPLOAD_FOLDER = _upload

    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    MAX_FILE_SIZE_IMAGE = 10 * 1024 * 1024
    MAX_FILE_SIZE_DOCUMENT = 15 * 1024 * 1024
    MAX_FILE_SIZE_PDF = 15 * 1024 * 1024
    MAX_FILE_SIZE_EXCEL = 10 * 1024 * 1024

    CLAMAV_ENABLED = os.environ.get('CLAMAV_ENABLED', 'False').lower() in ('true', '1', 'yes')
    CLAMAV_HOST = os.environ.get('CLAMAV_HOST', 'localhost')
    CLAMAV_PORT = int(os.environ.get('CLAMAV_PORT', '3310'))
    CLAMAV_TIMEOUT = int(os.environ.get('CLAMAV_TIMEOUT', '30'))

    # Local (desktop) : le schéma par défaut est HTTP. Aucun reverse proxy HTTPS.
    PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'http')

    # URI de redirection OAuth Google. Optionnelle : si absente, elle est
    # construite automatiquement à partir de l'URL locale (url_for _external).
    # À définir explicitement si l'auto-détection échoue.
    GOOGLE_OAUTH_REDIRECT_URI = os.environ.get('GOOGLE_OAUTH_REDIRECT_URI', '')

    # SameSite=Lax : requis pour que le cookie de session (porteur de l'état
    # OAuth) soit transmis lors de la redirection cross-site de Google vers le
    # callback. SameSite=Strict bloquerait le callback OAuth.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('true', '1', 'yes')
    PERMANENT_SESSION_LIFETIME = int(os.environ.get('PERMANENT_SESSION_LIFETIME', '1800'))

    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = os.environ.get('REMEMBER_COOKIE_SAMESITE', 'Strict')
    REMEMBER_COOKIE_SECURE = os.environ.get('REMEMBER_COOKIE_SECURE', 'False').lower() in ('true', '1', 'yes')
    REMEMBER_COOKIE_DURATION = int(os.environ.get('REMEMBER_COOKIE_DURATION', '86400'))

    WTF_CSRF_TIME_LIMIT = int(os.environ.get('WTF_CSRF_TIME_LIMIT', '1800'))
    WTF_CSRF_SSL_STRICT = True

    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')
