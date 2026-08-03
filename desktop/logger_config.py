import os
import logging
import logging.handlers
from datetime import datetime


LOG_DIR = None
_startup_logger = None
_configured = False


def ensure_log_dir(base_dir=None):
    global LOG_DIR
    if LOG_DIR:
        return LOG_DIR
    if base_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOG_DIR = os.path.join(base_dir, 'logs')
    os.makedirs(LOG_DIR, exist_ok=True)
    return LOG_DIR


def setup_logging(base_dir=None, debug=False):
    global _startup_logger, _configured
    if _configured:
        # Idempotent : plusieurs appels (tests, main(), sous-modules) ne
        # doivent NI doubler les handlers (lignes de log dupliquées) NI
        # recréer les fichiers de logs.
        return _startup_logger or logging.getLogger('startup')
    _configured = True

    log_dir = ensure_log_dir(base_dir)
    level = logging.DEBUG if debug else logging.INFO

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)-7s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    app_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'app.log'), maxBytes=5*1024*1024, backupCount=5,
        encoding='utf-8'
    )
    app_handler.setLevel(level)
    app_handler.setFormatter(formatter)

    error_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'error.log'), maxBytes=5*1024*1024, backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    startup_handler = logging.FileHandler(
        os.path.join(log_dir, 'startup.log'), encoding='utf-8'
    )
    startup_handler.setLevel(logging.DEBUG)
    startup_handler.setFormatter(formatter)

    security_handler = logging.FileHandler(
        os.path.join(log_dir, 'security.log'), encoding='utf-8'
    )
    security_handler.setLevel(logging.INFO)
    security_handler.setFormatter(formatter)

    security_logger = logging.getLogger('security')
    security_logger.setLevel(logging.INFO)
    security_logger.addHandler(security_handler)
    security_logger.propagate = False

    root = logging.getLogger()
    root.setLevel(level)
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.addHandler(app_handler)
    root.addHandler(error_handler)

    startup_logger = logging.getLogger('startup')
    startup_logger.setLevel(logging.DEBUG)
    startup_logger.addHandler(startup_handler)
    startup_logger.propagate = False

    if debug:
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        console.setFormatter(formatter)
        root.addHandler(console)

    _startup_logger = startup_logger

    startup_logger.info('=== CIENTO IMMOBILIER STARTUP ===')
    startup_logger.info(f'Version: 1.0.0')
    startup_logger.info(f'Log directory: {log_dir}')
    startup_logger.info(f'Debug mode: {debug}')

    return startup_logger


def get_startup_logger():
    return _startup_logger or logging.getLogger('startup')


def log_security(user_id, action, details=''):
    logger = logging.getLogger('security')
    logger.info(f'user={user_id} | action={action} | {details}')
