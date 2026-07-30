import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()

    if len(SECRET_KEY) < 32:
        import warnings
        warnings.warn('SECRET_KEY trop court ! Utilisez au moins 32 caractères.', stacklevel=2)

    db_user = os.environ.get('DB_USER', 'postgres')
    db_password = os.environ.get('DB_PASSWORD', 'postgres')
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_port = os.environ.get('DB_PORT', '5432')
    db_name = os.environ.get('DB_NAME', 'ciento_immobilier')

    database_url = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        SQLALCHEMY_DATABASE_URI = database_url
    else:
        SQLALCHEMY_DATABASE_URI = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER') or os.path.join(basedir, 'app', 'static', 'uploads')

    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    MAX_FILE_SIZE_IMAGE = 10 * 1024 * 1024
    MAX_FILE_SIZE_DOCUMENT = 15 * 1024 * 1024
    MAX_FILE_SIZE_PDF = 15 * 1024 * 1024
    MAX_FILE_SIZE_EXCEL = 10 * 1024 * 1024

    CLAMAV_ENABLED = os.environ.get('CLAMAV_ENABLED', 'False').lower() in ('true', '1', 'yes')
    CLAMAV_HOST = os.environ.get('CLAMAV_HOST', 'localhost')
    CLAMAV_PORT = int(os.environ.get('CLAMAV_PORT', '3310'))
    CLAMAV_TIMEOUT = int(os.environ.get('CLAMAV_TIMEOUT', '30'))

    PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'https')

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Strict')
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'True').lower() in ('true', '1', 'yes')
    PERMANENT_SESSION_LIFETIME = int(os.environ.get('PERMANENT_SESSION_LIFETIME', '1800'))

    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = os.environ.get('REMEMBER_COOKIE_SAMESITE', 'Strict')
    REMEMBER_COOKIE_SECURE = os.environ.get('REMEMBER_COOKIE_SECURE', 'True').lower() in ('true', '1', 'yes')
    REMEMBER_COOKIE_DURATION = int(os.environ.get('REMEMBER_COOKIE_DURATION', '86400'))

    WTF_CSRF_TIME_LIMIT = int(os.environ.get('WTF_CSRF_TIME_LIMIT', '1800'))
    WTF_CSRF_SSL_STRICT = True

    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')

    if not DEBUG:
        SESSION_COOKIE_SECURE = True
        REMEMBER_COOKIE_SECURE = True
