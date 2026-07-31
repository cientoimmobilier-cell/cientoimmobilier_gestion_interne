import os
import sys
import shutil
import logging
import subprocess
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class StartupChecker:

    REQUIRED_DIRS = [
        'app/static/uploads',
        'app/static/uploads/photos',
        'app/static/uploads/documents',
        'exports',
        'backups',
        'logs',
        'temp',
    ]

    REQUIRED_ENV_VARS = [
        'DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'DB_NAME', 'SECRET_KEY'
    ]

    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.errors = []
        self.warnings = []

    def _env_dir(self):
        """Répertoire contenant le .env réellement chargé par config.py.

        En mode PyInstaller onefile, config.py lit le .env empaqueté dans
        sys._MEIPASS ; les contrôles doivent donc cibler le même fichier
        et non un .env d'exemple posé à côté de l'exe.
        """
        if getattr(sys, 'frozen', False):
            return getattr(sys, '_MEIPASS', self.base_dir)
        return self.base_dir

    def check_all(self):
        self._check_directories()
        self._check_env_file()
        self._check_postgresql()
        self._check_migrations()
        return len(self.errors) == 0

    def _check_directories(self):
        for rel_dir in self.REQUIRED_DIRS:
            abs_dir = os.path.join(self.base_dir, rel_dir)
            try:
                os.makedirs(abs_dir, exist_ok=True)
                if not os.access(abs_dir, os.W_OK):
                    self.warnings.append(f'No write permission: {rel_dir}')
            except Exception as e:
                self.errors.append(f'Cannot create directory {rel_dir}: {e}')

    def _check_env_file(self):
        env_path = os.path.join(self._env_dir(), '.env')
        if not os.path.exists(env_path):
            self.errors.append('.env file not found')
            return

        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()

        missing = []
        for var in self.REQUIRED_ENV_VARS:
            if f'{var}=' not in content:
                missing.append(var)
        if missing:
            self.errors.append(f'Missing environment variables: {", ".join(missing)}')

    def _check_postgresql(self):
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(self._env_dir(), '.env'))

            db_host = os.environ.get('DB_HOST', 'localhost')
            db_port = os.environ.get('DB_PORT', '5432')
            db_name = os.environ.get('DB_NAME', 'ciento_immobilier_db')
            db_user = os.environ.get('DB_USER', 'postgres')

            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                result = sock.connect_ex((db_host, int(db_port)))
                if result != 0:
                    self.errors.append(
                        f'PostgreSQL is not reachable at {db_host}:{db_port}. '
                        f'Please start the PostgreSQL service.'
                    )
                    return
            logger.info(f'PostgreSQL is reachable at {db_host}:{db_port}')

            import psycopg2
            db_password = os.environ.get('DB_PASSWORD', 'postgres')
            conn = psycopg2.connect(
                host=db_host, port=db_port,
                user=db_user, password=db_password,
                dbname=db_name, connect_timeout=5
            )
            conn.close()
            logger.info(f'Database {db_name} connection OK')

        except ImportError as e:
            self.warnings.append(f'Missing dependency: {e}')
        except Exception as e:
            self.errors.append(f'Database connection failed: {e}')

    def _check_migrations(self):
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(self._env_dir(), '.env'))
            from app import create_app, db
            app = create_app()
            with app.app_context():
                from sqlalchemy import inspect
                inspector = inspect(db.engine)
                tables = inspector.get_table_names()
                required_tables = ['utilisateurs', 'clients', 'proprietes',
                                   'transactions', 'occupations']
                missing = [t for t in required_tables if t not in tables]
                if missing:
                    self.warnings.append(
                        f'Missing tables: {", ".join(missing)}. '
                        f'Run: python init_db.py'
                    )
                else:
                    logger.info(f'Database schema OK — {len(tables)} tables found')
        except Exception as e:
            self.warnings.append(f'Migration check failed: {e}')
