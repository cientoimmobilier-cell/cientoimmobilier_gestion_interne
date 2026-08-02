"""Tests du module Sauvegarde Cloud Google Drive (AES-256, exports, backup/restore)."""
import base64
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import create_app, db
from config import Config
from app.models import (
    Client, CloudBackupRecord, CloudBackupSchedule, CloudBackupSetting,
    Utilisateur,
)
from app.services import backup_service, crypto_service, export_service
from app.services.scheduler_service import compute_next_run
from app.routes.cloud_backup import _redirect_uri


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = 'cle-de-test-ciento-immobilier-2026-32caracteres'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


PASSPHRASE = 'phrase-de-teste-ciento'


class _FakeDelete:
    def __init__(self, owner, file_id):
        self.owner = owner
        self.file_id = file_id

    def execute(self):
        self.owner.store.pop(self.file_id, None)


class FakeDriveFiles:
    def __init__(self, owner):
        self.owner = owner

    def delete(self, fileId):
        return _FakeDelete(self.owner, fileId)


class FakeDrive:
    """Simulation minimale de l'API Drive v3 pour les tests hors ligne."""

    def __init__(self):
        self.store = {}
        self._next_id = 1

    def files(self):
        return FakeDriveFiles(self)

    def create(self, body, media_body, fields):
        class _Request:
            def __init__(self, owner, media_body):
                self.owner = owner
                self.media = media_body
                self.started = False

            def next_chunk(self, num_retries=3):
                if self.started:
                    return None, None
                self.started = True
                self.owner._next_id += 1
                file_id = f'fake_file_{self.owner._next_id}'
                self.owner.store[file_id] = self.media._fd.read() \
                    if hasattr(self.media, '_fd') else b''
                return None, {'id': file_id}
        return _Request(self, media_body)


class FakeGoogleDriveService:
    _shared_drive = None

    @classmethod
    def reset_drive(cls):
        cls._shared_drive = FakeDrive()

    def __init__(self, setting=None):
        self.setting = setting
        if FakeGoogleDriveService._shared_drive is None:
            FakeGoogleDriveService.reset_drive()
        self.drive = FakeGoogleDriveService._shared_drive

    def build_service(self):
        return self.drive

    def ensure_backup_tree(self, drive=None):
        return {'Daily': 'f_daily', 'Weekly': 'f_weekly',
                'Monthly': 'f_monthly', 'Archive': 'f_archive'}

    def upload(self, drive, path, folder_id, mime, progress_cb=None):
        with open(path, 'rb') as fh:
            data = fh.read()
        drive._next_id += 1
        file_id = f'fake_file_{drive._next_id}'
        drive.store[file_id] = data
        if progress_cb:
            progress_cb(len(data), len(data), 0.05)
        return file_id

    def get_account_email(self, drive=None):
        return 'cloud@test.local'

    def download(self, drive, file_id, dest_path):
        with open(dest_path, 'wb') as fh:
            fh.write(drive.store[file_id])

    def delete(self, drive, file_id):
        drive.store.pop(file_id, None)


class CloudBackupTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        self._upload_dir = tempfile.mkdtemp(prefix='ciento_uploads_')
        self.app.config['UPLOAD_FOLDER'] = self._upload_dir
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        shutil.rmtree(self._upload_dir, ignore_errors=True)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _login_admin(self):
        admin = Utilisateur(
            nom='Admin', prenom='Test', email='admin@ciento.immo',
            role='Administrateur')
        admin.set_password('adminpassword123')
        db.session.add(admin)
        db.session.commit()
        return self.client.post('/login', data={
            'email': 'admin@ciento.immo', 'password': 'adminpassword123'})

    def _seed_data(self):
        db.session.add_all([
            Client(code_client='CLI-T1', nom='MARTIN', prenom='Thomas',
                   email='thomas@test.local'),
            Client(code_client='CLI-T2', nom='DURAND', prenom='Marie',
                   email='marie@test.local'),
        ])
        db.session.commit()

    def _enable_setting(self):
        setting = CloudBackupSetting.get()
        setting.encryption_passphrase_wrapped = crypto_service.wrap_secret(PASSPHRASE)
        db.session.commit()
        return setting

    # ── Chiffrement ──────────────────────────────────────────────────────────
    def test_crypto_roundtrip(self):
        data = b'contenu confidentiel ' + bytes(range(256))
        encrypted = crypto_service.encrypt_bytes(data, PASSPHRASE)
        self.assertNotIn(b'contenu confidentiel', encrypted)
        self.assertEqual(crypto_service.decrypt_bytes(encrypted, PASSPHRASE), data)

    def test_crypto_wrong_passphrase(self):
        encrypted = crypto_service.encrypt_bytes(b'secret', PASSPHRASE)
        with self.assertRaises(crypto_service.CryptoError):
            crypto_service.decrypt_bytes(encrypted, 'mauvaise-phrase-xxx')

    def test_crypto_tampered_payload(self):
        encrypted = bytearray(crypto_service.encrypt_bytes(b'secret', PASSPHRASE))
        encrypted[-1] ^= 0xFF
        with self.assertRaises(crypto_service.CryptoError):
            crypto_service.decrypt_bytes(bytes(encrypted), PASSPHRASE)

    def test_wrap_unwrap_secret(self):
        wrapped = crypto_service.wrap_secret('GOCSPX-very-secret')
        self.assertNotIn('GOCSPX', wrapped)
        self.assertEqual(crypto_service.unwrap_secret(wrapped), 'GOCSPX-very-secret')
        self.assertIsNone(crypto_service.unwrap_secret(None))

    # ── Planification ────────────────────────────────────────────────────────
    def test_schedule_compute_next_run(self):
        base = datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)  # jeudi
        hourly = compute_next_run('hourly', from_time=base)
        self.assertEqual(hourly, datetime(2026, 1, 15, 11, 0, tzinfo=timezone.utc))
        daily = compute_next_run('daily', hour=2, minute=0, from_time=base)
        self.assertEqual(daily, datetime(2026, 1, 16, 2, 0, tzinfo=timezone.utc))
        daily_past = compute_next_run('daily', hour=10, minute=0, from_time=base)
        self.assertEqual(daily_past, datetime(2026, 1, 16, 10, 0, tzinfo=timezone.utc))
        weekly = compute_next_run('weekly', day_of_week=0, hour=2, minute=0,
                                  from_time=base)  # lundi suivant (19/01)
        self.assertEqual(weekly, datetime(2026, 1, 19, 2, 0, tzinfo=timezone.utc))
        monthly = compute_next_run('monthly', day_of_month=1, hour=2, minute=0,
                                   from_time=base)
        self.assertEqual(monthly, datetime(2026, 2, 1, 2, 0, tzinfo=timezone.utc))

    # ── Exports ──────────────────────────────────────────────────────────────
    def test_exports_generate_data(self):
        self._seed_data()
        self.assertIn(b'MARTIN', export_service.export_csv('clients'))
        self.assertGreater(len(export_service.export_excel('clients')), 0)
        self.assertGreater(len(export_service.export_pdf('clients')), 0)
        self.assertIn(b'CLI-T2', export_service.export_csv('clients'))

    def test_sql_dump_and_restore(self):
        self._seed_data()
        dump = export_service.export_sql()
        self.assertIn('CREATE TABLE', dump)
        self.assertIn('CLI-T1', dump)
        self.assertIn('CLI-T2', dump)

        # On vide puis on restaure via le dump
        from app.services.backup_service import execute_sql_script
        db.session.remove()
        with db.engine.connect() as conn:
            conn.execution_options(isolation_level='AUTOCOMMIT')
            execute_sql_script(conn, 'DELETE FROM clients;')
        db.session.remove()
        with db.engine.connect() as conn:
            conn.execution_options(isolation_level='AUTOCOMMIT')
            execute_sql_script(conn, dump)
        db.session.remove()
        clients = db.session.execute(select(Client)).scalars().all()
        self.assertEqual(len(clients), 2)
        self.assertEqual(clients[0].code_client, 'CLI-T1')

    # ── Backup / restauration (Drive simulé) ────────────────────────────────
    def test_restore_upload_files_blocks_zip_slip(self):
        from app.services.backup_service import _restore_upload_files
        import io
        import zipfile as zf_mod

        target = os.path.join(self._upload_dir, 'out')
        os.makedirs(target)
        buf = io.BytesIO()
        with zf_mod.ZipFile(buf, 'w') as zf:
            zf.writestr('uploads/normal.png', b'ok')
            zf.writestr('uploads/../../evil.txt', b'boom')
        buf.seek(0)
        with zf_mod.ZipFile(buf) as zf:
            count = _restore_upload_files(zf, 'uploads', target)
        self.assertEqual(count, 1)
        self.assertTrue(os.path.exists(os.path.join(target, 'normal.png')))
        self.assertFalse(os.path.exists(os.path.join(
            self._upload_dir, 'evil.txt')))

    def test_backup_flow_and_restore(self):
        self._seed_data()
        self._enable_setting()

        original_class = backup_service.GoogleDriveService
        backup_service.GoogleDriveService = FakeGoogleDriveService
        FakeGoogleDriveService.reset_drive()
        try:
            self._upload_photo = os.path.join(
                self._upload_dir, 'photos', 'test_photo.png')
            os.makedirs(os.path.dirname(self._upload_photo), exist_ok=True)
            with open(self._upload_photo, 'wb') as fh:
                fh.write(b'FAKE-PHOTO')

            service = backup_service.BackupService(self.app)
            service.progress.create('job-1')
            service._run_backup('job-1', 'Manual', 'Testeur', 'all')

            record = db.session.execute(select(CloudBackupRecord)).scalars().first()
            self.assertIsNotNone(record)
            self.assertEqual(record.status, 'success')
            self.assertEqual(record.drive_folder, 'Archive')
            self.assertIsNotNone(record.drive_file_id)
            self.assertGreater(record.size_bytes, 0)
            self.assertGreaterEqual(record.file_count, 8 + 3 + 1)  # rapports*3 + sql + infos + upload

            status = service.progress.get('job-1')
            self.assertEqual(status['status'], 'success')

            # On supprime les données ET les fichiers téléversés puis on restaure
            os.remove(self._upload_photo)
            db.session.execute(Client.__table__.delete())
            db.session.commit()
            self.assertEqual(
                len(db.session.execute(select(Client)).scalars().all()), 0)
            self.assertFalse(os.path.exists(self._upload_photo))

            service.restore_backup(record.id, PASSPHRASE)
            clients = db.session.execute(select(Client)).scalars().all()
            self.assertEqual(len(clients), 2)
            with open(self._upload_photo, 'rb') as fh:
                self.assertEqual(fh.read(), b'FAKE-PHOTO')
        finally:
            backup_service.GoogleDriveService = original_class

    def test_backup_fails_without_passphrase(self):
        # Aucune phrase de passe définie → la sauvegarde échoue proprement
        service = backup_service.BackupService(self.app)
        service.progress.create('job-fail')
        service._run_backup('job-fail', 'Manual', 'Testeur', 'all')
        record = db.session.execute(select(CloudBackupRecord)).scalars().first()
        self.assertEqual(record.status, 'failed')
        self.assertIn('phrase de passe', record.message.lower())
        self.assertEqual(service.progress.get('job-fail')['status'], 'failed')

    def test_backup_wrong_passphrase(self):
        self._seed_data()
        self._enable_setting()
        original_class = backup_service.GoogleDriveService
        backup_service.GoogleDriveService = FakeGoogleDriveService
        FakeGoogleDriveService.reset_drive()
        try:
            service = backup_service.BackupService(self.app)
            service.progress.create('job-2')
            service._run_backup('job-2', 'Manual', 'Testeur', 'all')
            record = db.session.execute(select(CloudBackupRecord)).scalars().first()
            db.session.remove()
            with self.assertRaises(Exception):
                service.restore_backup(record.id, 'mauvaise-phrase-xxx')
        finally:
            backup_service.GoogleDriveService = original_class

    def test_retention(self):
        self._enable_setting()
        drive = FakeDrive()
        drive.store['old_id'] = b'old'
        drive.store['new_id'] = b'new'
        now = datetime.now(timezone.utc)
        old = CloudBackupRecord(backup_type='Daily', status='success',
                                drive_folder='Daily', drive_file_id='old_id',
                                started_at=now, finished_at=now)
        new = CloudBackupRecord(backup_type='Daily', status='success',
                                drive_folder='Daily', drive_file_id='new_id',
                                started_at=now, finished_at=now + timedelta(minutes=1))
        db.session.add_all([old, new])
        db.session.commit()
        service = backup_service.BackupService(self.app)
        service.apply_retention(drive, 'Daily', 1)
        self.assertIn('new_id', drive.store)
        self.assertNotIn('old_id', drive.store)

    # ── B11 : verrou d'exécution partagé backup/restore ─────────────────────
    def test_restore_blocked_while_backup_running(self):
        from app.services.google_drive_service import GoogleDriveError
        service = backup_service.BackupService(self.app)
        service._execution_lock.acquire()
        try:
            with self.assertRaises(GoogleDriveError):
                service.restore_backup(9999, PASSPHRASE)
        finally:
            service._execution_lock.release()

    def test_restore_releases_lock_after_failure(self):
        from app.services.google_drive_service import GoogleDriveError
        service = backup_service.BackupService(self.app)
        # Fichier introuvable → échec avant même de lever le verrou, qui doit
        # néanmoins être libéré pour les opérations suivantes.
        with self.assertRaises(GoogleDriveError):
            service.restore_backup(424242, PASSPHRASE)
        self.assertFalse(service._execution_lock.locked())

    # ── Routes ───────────────────────────────────────────────────────────────
    def test_index_page_requires_admin(self):
        self._login_admin()
        response = self.client.get('/parametres/sauvegarde-cloud/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Sauvegarde Cloud', response.data)

    def test_index_page_denied_for_agent(self):
        agent = Utilisateur(nom='Agent', prenom='X', email='agent@ciento.immo',
                            role='Agent immobilier')
        agent.set_password('agentpass123')
        db.session.add(agent)
        db.session.commit()
        self.client.post('/login', data={'email': 'agent@ciento.immo',
                                         'password': 'agentpass123'})
        response = self.client.get('/parametres/sauvegarde-cloud/', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'Tableau de bord des sauvegardes', response.data)

    def test_manual_backup_requires_ready_setup(self):
        self._login_admin()
        self._enable_setting()
        response = self.client.post('/parametres/sauvegarde-cloud/backup',
                                    data={'backup_type': 'Manual'},
                                    follow_redirects=True)
        self.assertIn(b'Connectez d', response.data)

    # ── B7 : changement de phrase de passe ───────────────────────────────────
    def test_set_passphrase_first_time(self):
        self._login_admin()
        response = self.client.post(
            '/parametres/sauvegarde-cloud/cle',
            data={'passphrase': 'nouvelle-phrase-098',
                  'confirmation': 'nouvelle-phrase-098'},
            follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        setting = CloudBackupSetting.get()
        self.assertEqual(
            crypto_service.unwrap_secret(setting.encryption_passphrase_wrapped),
            'nouvelle-phrase-098')

    def test_change_passphrase_requires_old(self):
        self._enable_setting()
        self._login_admin()
        response = self.client.post(
            '/parametres/sauvegarde-cloud/cle',
            data={'passphrase': 'nouvelle-phrase-098',
                  'confirmation': 'nouvelle-phrase-098'},
            follow_redirects=True)
        self.assertIn(b'ancienne phrase de passe', response.data)
        setting = CloudBackupSetting.get()
        self.assertEqual(
            crypto_service.unwrap_secret(setting.encryption_passphrase_wrapped),
            PASSPHRASE)

    def test_change_passphrase_rejects_wrong_old(self):
        self._enable_setting()
        self._login_admin()
        response = self.client.post(
            '/parametres/sauvegarde-cloud/cle',
            data={'old_passphrase': 'mauvaise-ancienne-xxx',
                  'passphrase': 'nouvelle-phrase-098',
                  'confirmation': 'nouvelle-phrase-098'},
            follow_redirects=True)
        self.assertIn(b'incorrecte', response.data)
        setting = CloudBackupSetting.get()
        self.assertEqual(
            crypto_service.unwrap_secret(setting.encryption_passphrase_wrapped),
            PASSPHRASE)

    def test_change_passphrase_with_correct_old(self):
        self._enable_setting()
        self._login_admin()
        response = self.client.post(
            '/parametres/sauvegarde-cloud/cle',
            data={'old_passphrase': PASSPHRASE,
                  'passphrase': 'nouvelle-phrase-098',
                  'confirmation': 'nouvelle-phrase-098'},
            follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        setting = CloudBackupSetting.get()
        self.assertEqual(
            crypto_service.unwrap_secret(setting.encryption_passphrase_wrapped),
            'nouvelle-phrase-098')

    # ── V4 : PKCE ────────────────────────────────────────────────────────────
    def test_pkce_pair_generation(self):
        from app.services.google_drive_service import GoogleDriveService
        import hashlib
        verifier, challenge = GoogleDriveService._pkce_pair()
        self.assertTrue(verifier)
        self.assertTrue(challenge)
        self.assertNotIn('=', challenge)
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode()
        self.assertEqual(challenge, expected)
        self.assertNotEqual(GoogleDriveService._pkce_pair()[0], verifier)

    def test_backups_page(self):
        self._login_admin()
        response = self.client.get('/parametres/sauvegarde-cloud/sauvegardes')
        self.assertEqual(response.status_code, 200)
        response = self.client.get('/parametres/sauvegarde-cloud/historique')
        self.assertEqual(response.status_code, 200)

    def test_status_endpoint_serializes(self):
        self._login_admin()
        from app.services.backup_service import BackupService
        service = BackupService(self.app)
        self.app.extensions['backup_service'] = service
        service.progress.create('job-json')
        service.progress.update('job-json', status='running', progress=42,
                                message='test', uploaded=1000, total_bytes=2000,
                                speed=50, eta=20)
        response = self.client.get('/parametres/sauvegarde-cloud/statut/job-json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['progress'], 42)

    # ── OAuth (étape 1 : SameSite + URL locale + redirect URI) ─────────────
    def test_config_samesite_is_lax(self):
        from config import Config as RealConfig
        self.assertEqual(RealConfig.SESSION_COOKIE_SAMESITE, 'Lax')

    def test_no_proxyfix_middleware(self):
        # Application 100 % locale (desktop) : aucun reverse proxy à envelopper.
        from werkzeug.middleware.proxy_fix import ProxyFix
        self.assertNotIsInstance(self.app.wsgi_app, ProxyFix)

    def test_local_http_scheme(self):
        # Schéma par défaut HTTP (localhost), pas de proxy HTTPS.
        from flask import request
        with self.app.test_request_context('/', environ_base={'HTTP_HOST': '127.0.0.1'}):
            self.assertEqual(request.scheme, 'http')
        self.assertEqual(self.app.config['PREFERRED_URL_SCHEME'], 'http')

    def test_redirect_uri_override(self):
        from flask import url_for
        with self.app.app_context():
            self.app.config['GOOGLE_OAUTH_REDIRECT_URI'] = \
                'http://127.0.0.1:5000/parametres/sauvegarde-cloud/callback'
            self.assertEqual(_redirect_uri(), self.app.config['GOOGLE_OAUTH_REDIRECT_URI'])

    def test_oauth_connect_saves_state_and_redirects(self):
        import app.routes.cloud_backup as cb

        class FakeOAuth:
            def __init__(self, setting=None):
                pass

            def is_configured(self):
                return True

            def authorization_url(self, redirect_uri):
                return ('https://accounts.google.com/o/oauth2/auth?x=1',
                        'state-xyz', 'pkce-verifier-abc')

        original = cb.GoogleDriveService
        cb.GoogleDriveService = FakeOAuth
        try:
            self._login_admin()
            resp = self.client.get('/parametres/sauvegarde-cloud/connexion')
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(
                resp.headers['Location'].startswith(
                    'https://accounts.google.com/o/oauth2/auth'))
            with self.client.session_transaction() as sess:
                self.assertEqual(sess['cloud_oauth_state'], 'state-xyz')
                self.assertEqual(sess['cloud_oauth_verifier'], 'pkce-verifier-abc')
        finally:
            cb.GoogleDriveService = original

    def test_oauth_callback_success(self):
        import app.routes.cloud_backup as cb

        class FakeOAuth:
            exchanged = []

            def __init__(self, setting=None):
                pass

            def is_connected(self):
                return False

            def is_configured(self):
                return False

            def exchange_code(self, code, redirect_uri, code_verifier=None):
                self.exchanged.append((code, redirect_uri, code_verifier))

        original = cb.GoogleDriveService
        cb.GoogleDriveService = FakeOAuth
        try:
            self._login_admin()
            with self.client.session_transaction() as sess:
                sess['cloud_oauth_state'] = 'state-xyz'
                sess['cloud_oauth_verifier'] = 'pkce-verifier-abc'
            resp = self.client.get(
                '/parametres/sauvegarde-cloud/callback',
                query_string={'state': 'state-xyz', 'code': 'auth-code-123'})
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(FakeOAuth.exchanged)
            self.assertEqual(FakeOAuth.exchanged[0][0], 'auth-code-123')
            self.assertIn('/parametres/sauvegarde-cloud/callback',
                          FakeOAuth.exchanged[0][1])
            self.assertEqual(FakeOAuth.exchanged[0][2], 'pkce-verifier-abc')
        finally:
            cb.GoogleDriveService = original

    def test_oauth_callback_rejects_wrong_state(self):
        import app.routes.cloud_backup as cb

        class FakeOAuth:
            exchanged = []

            def __init__(self, setting=None):
                pass

            def is_connected(self):
                return False

            def is_configured(self):
                return False

            def exchange_code(self, code, redirect_uri, code_verifier=None):
                self.exchanged.append((code, redirect_uri, code_verifier))

        original = cb.GoogleDriveService
        cb.GoogleDriveService = FakeOAuth
        try:
            self._login_admin()
            with self.client.session_transaction() as sess:
                sess['cloud_oauth_state'] = 'expected-state'
            resp = self.client.get(
                '/parametres/sauvegarde-cloud/callback',
                query_string={'state': 'evil-state', 'code': 'auth-code-123'},
                follow_redirects=True)
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(FakeOAuth.exchanged)
            self.assertIn(b'session incorrect', resp.data)
        finally:
            cb.GoogleDriveService = original

    def test_oauth_disconnect_clears_credentials(self):
        import app.routes.cloud_backup as cb

        class FakeOAuth:
            cleared = []
            revoked = []

            def __init__(self, setting=None):
                pass

            def is_connected(self):
                return False

            def is_configured(self):
                return False

            def revoke_refresh_token(self):
                self.revoked.append(True)

            def clear_credentials(self):
                self.cleared.append(True)

        original = cb.GoogleDriveService
        cb.GoogleDriveService = FakeOAuth
        try:
            self._login_admin()
            resp = self.client.post(
                '/parametres/sauvegarde-cloud/deconnexion',
                follow_redirects=True)
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(FakeOAuth.cleared)
            self.assertTrue(FakeOAuth.revoked)
        finally:
            cb.GoogleDriveService = original


class TestRestoreSqlValidation(unittest.TestCase):
    """Garde-fou : le script SQL de restauration doit être conforme à l'export."""

    def test_accepts_legitimate_export(self):
        from app.services.backup_service import _validate_restore_sql
        legit = (
            '-- CIENTO IMMOBILIER — Sauvegarde de la base de données\n'
            'BEGIN;\n'
            'DROP TABLE IF EXISTS "contrats" CASCADE;\n'
            'CREATE TABLE "contrats" (id INTEGER PRIMARY KEY, '
            'numero_contrat VARCHAR(50) NOT NULL, '
            'transaction_id INTEGER, FOREIGN KEY(transaction_id) '
            'REFERENCES "transactions" (id) ON DELETE CASCADE);\n'
            "INSERT INTO \"contrats\" (id, numero_contrat) VALUES (1, 'C-001');\n"
            "SELECT setval(pg_get_serial_sequence('contrats', 'id'), 1);\n"
            'COMMIT;'
        )
        _validate_restore_sql(legit)

    def test_rejects_copy_to(self):
        from app.services.backup_service import _validate_restore_sql
        from app.services.google_drive_service import GoogleDriveError
        with self.assertRaises(GoogleDriveError):
            _validate_restore_sql("COPY contrats TO '/tmp/out.csv';")

    def test_rejects_drop_database(self):
        from app.services.backup_service import _validate_restore_sql
        from app.services.google_drive_service import GoogleDriveError
        with self.assertRaises(GoogleDriveError):
            _validate_restore_sql('DROP DATABASE ciento;')

    def test_rejects_delete_from(self):
        from app.services.backup_service import _validate_restore_sql
        from app.services.google_drive_service import GoogleDriveError
        with self.assertRaises(GoogleDriveError):
            _validate_restore_sql('DELETE FROM "utilisateurs";')

    def test_rejects_alter_and_grant(self):
        from app.services.backup_service import _validate_restore_sql
        from app.services.google_drive_service import GoogleDriveError
        with self.assertRaises(GoogleDriveError):
            _validate_restore_sql('ALTER SYSTEM SET listen_addresses;')
        with self.assertRaises(GoogleDriveError):
            _validate_restore_sql('GRANT ALL ON ALL TABLES TO public;')


if __name__ == '__main__':
    unittest.main()
