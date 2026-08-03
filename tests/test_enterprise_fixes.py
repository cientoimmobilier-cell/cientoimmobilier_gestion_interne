"""Tests de non-régression pour la remédiation Enterprise (FIX 1 à 20).

Couvre : planificateur naïf/aware, garde-fou SQL (bypass par commentaires),
zip-slip réel, _to_number Excel, disponibilité serveur transaction,
rétention en cas d'échec Drive, repli de port borné, journalisation
idempotente et synchronisation de schéma migrate_db.
"""
import logging
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import inspect, select

from app import create_app, db
from config import Config
from app.models import (
    Client, CloudBackupRecord, CloudBackupSchedule, Propriete, Transaction,
    Utilisateur,
)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = 'cle-de-test-ciento-immobilier-2026-32caracteres'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


class EnterpriseFixesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        self._upload_dir = tempfile.mkdtemp(prefix='ciento_fixes_')
        self.app.config['UPLOAD_FOLDER'] = self._upload_dir
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        shutil.rmtree(self._upload_dir, ignore_errors=True)

    def _login_agent(self, email='agent.fix@ciento.immo'):
        agent = Utilisateur(nom='Fix', prenom='Agent', email=email,
                            role='Agent immobilier')
        agent.set_password('agentpass123')
        db.session.add(agent)
        db.session.commit()
        return self.client.post('/login', data={
            'email': email, 'password': 'agentpass123'})

    def _seed_client_and_property(self, statut='Disponible'):
        client = Client(code_client='CLI-FIX', nom='TEST', prenom='Client',
                        email='client.fix@test.local')
        prop = Propriete(reference_bien='B-FIX', titre='Villa test',
                         type_bien='Villa', type_operation='Vente',
                         prix=Decimal('150000.00'), statut=statut)
        db.session.add_all([client, prop])
        db.session.commit()
        return client, prop

    # ── FIX 1 : planificateur — comparaison UTC naïf (plus de TypeError) ──
    def test_scheduler_tick_no_typeerror_with_naive_next_run(self):
        import app.services.scheduler_service as sched
        calls = []

        class _StubService:
            def __init__(self, *a, **k):
                pass

            def run_manual_backup(self, *a, **k):
                calls.append(a)

        schedule = CloudBackupSchedule.get()
        schedule.enabled = True
        schedule.frequency = 'daily'
        schedule.hour = 2
        schedule.minute = 0
        schedule.next_run_at = datetime(2020, 1, 1, 2, 0)
        db.session.commit()

        original = sched.BackupService
        sched.BackupService = _StubService
        try:
            scheduler = sched.BackupScheduler()
            scheduler._tick(self.app)
            self.assertTrue(calls, 'la sauvegarde due doit être déclenchée')
            updated = CloudBackupSchedule.get()
            self.assertIsInstance(updated.next_run_at, datetime)
            self.assertGreater(updated.next_run_at,
                               datetime.now(timezone.utc).replace(tzinfo=None))
        finally:
            sched.BackupService = original

    def test_scheduler_tick_skips_future_naive_next_run(self):
        import app.services.scheduler_service as sched
        calls = []

        class _StubService:
            def __init__(self, *a, **k):
                pass

            def run_manual_backup(self, *a, **k):
                calls.append(a)

        schedule = CloudBackupSchedule.get()
        schedule.enabled = True
        schedule.frequency = 'daily'
        schedule.next_run_at = datetime(2099, 1, 1, 2, 0)
        db.session.commit()

        original = sched.BackupService
        sched.BackupService = _StubService
        try:
            sched.BackupScheduler()._tick(self.app)
            self.assertFalse(calls, 'aucune sauvegarde si l’échéance est future')
        finally:
            sched.BackupService = original

    def test_compute_next_run_accepts_naive_from_time(self):
        from app.services.scheduler_service import compute_next_run
        naive = datetime(2026, 1, 15, 10, 30)
        result = compute_next_run('daily', hour=2, minute=0, from_time=naive)
        self.assertEqual(result, datetime(2026, 1, 16, 2, 0))

    # ── FIX 8 : garde-fou SQL — bypass par commentaires bloqué ────────────
    def test_restore_sql_rejects_block_comment_bypass(self):
        from app.services.backup_service import _validate_restore_sql
        from app.services.google_drive_service import GoogleDriveError
        with self.assertRaises(GoogleDriveError):
            _validate_restore_sql('DELETE/**/FROM "clients";')

    def test_restore_sql_rejects_line_comment_then_delete(self):
        from app.services.backup_service import _validate_restore_sql
        from app.services.google_drive_service import GoogleDriveError
        with self.assertRaises(GoogleDriveError):
            _validate_restore_sql('-- note trompeuse\nDELETE FROM "clients";')

    def test_restore_sql_rejects_copy_to_with_comment(self):
        from app.services.backup_service import _validate_restore_sql
        from app.services.google_drive_service import GoogleDriveError
        with self.assertRaises(GoogleDriveError):
            _validate_restore_sql("COPY /*x*/ clients TO '/tmp/out.csv';")

    def test_restore_sql_rejects_comment_before_alter(self):
        from app.services.backup_service import _validate_restore_sql
        from app.services.google_drive_service import GoogleDriveError
        with self.assertRaises(GoogleDriveError):
            _validate_restore_sql('ALTER/**/SYSTEM SET listen_addresses;')

    # ── FIX 7 : restauration — extraction zip-slip (chemins réels) ────────
    def test_restore_upload_files_blocks_symlink_traversal(self):
        from app.services.backup_service import _restore_upload_files
        import io
        import zipfile as zf_mod

        target = os.path.join(self._upload_dir, 'out')
        os.makedirs(target)
        buf = io.BytesIO()
        with zf_mod.ZipFile(buf, 'w') as zf:
            zf.writestr('uploads/pic.png', b'img')
            zf.writestr('uploads/../../../../pwned.txt', b'evil')
        buf.seek(0)
        with zf_mod.ZipFile(buf) as zf:
            count = _restore_upload_files(zf, 'uploads', target)
        self.assertEqual(count, 1)
        self.assertTrue(os.path.exists(os.path.join(target, 'pic.png')))
        self.assertFalse(os.path.exists(os.path.join(
            self._upload_dir, 'pwned.txt')))

    # ── FIX 11 : Excel — conversion numérique tolérante ───────────────────
    def test_excel_to_number_variants(self):
        from app.services.excel_service import _to_number
        self.assertEqual(_to_number('1 500,50 €'), 1500.5)
        self.assertEqual(_to_number('1500'), 1500.0)
        self.assertEqual(_to_number('1 500'), 1500.0)
        self.assertEqual(_to_number(42), 42.0)
        self.assertEqual(_to_number(None), None)
        self.assertEqual(_to_number(''), None)
        self.assertEqual(_to_number('abc'), None)

    # ── FIX 9 : transaction — garde serveur sur la disponibilité ─────────
    def test_transaction_blocked_when_property_unavailable(self):
        self._login_agent()
        client, prop = self._seed_client_and_property(statut='Réservé')
        agent_id = db.session.execute(
            select(Utilisateur.id).where(Utilisateur.role == 'Agent immobilier')
        ).scalar()
        resp = self.client.post(
            '/transactions/ajouter',
            data={'client_id': client.id, 'propriete_id': prop.id,
                  'agent_id': agent_id, 'type_transaction': 'Vente',
                  'montant': '150000', 'date_transaction': '2026-01-10',
                  'pourcentage_commission': '5', 'devise': 'EUR'},
            follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'n&#39;est plus disponible', resp.data)
        transactions = db.session.execute(select(Transaction)).scalars().all()
        self.assertEqual(transactions, [])
        self.assertEqual(db.session.get(Propriete, prop.id).statut, 'Réservé')

    def test_transaction_ok_reserves_available_property(self):
        self._login_agent()
        client, prop = self._seed_client_and_property(statut='Disponible')
        agent_id = db.session.execute(
            select(Utilisateur.id).where(Utilisateur.role == 'Agent immobilier')
        ).scalar()
        resp = self.client.post(
            '/transactions/ajouter',
            data={'client_id': client.id, 'propriete_id': prop.id,
                  'agent_id': agent_id, 'type_transaction': 'Vente',
                  'montant': '150000', 'date_transaction': '2026-01-10',
                  'pourcentage_commission': '5', 'devise': 'EUR'})
        self.assertEqual(resp.status_code, 302)
        tx = db.session.execute(select(Transaction)).scalars().first()
        self.assertIsNotNone(tx)
        self.assertEqual(db.session.get(Propriete, prop.id).statut, 'Réservé')

    # ── FIX 5 : rétention — drive_file_id conservé si la suppression échoue
    def test_retention_keeps_drive_file_id_on_delete_failure(self):
        from app.services.backup_service import BackupService
        now = datetime.now(timezone.utc)
        old = CloudBackupRecord(backup_type='Daily', status='success',
                                drive_folder='Daily', drive_file_id='old_id',
                                started_at=now, finished_at=now)
        newer = CloudBackupRecord(backup_type='Daily', status='success',
                                  drive_folder='Daily', drive_file_id='new_id',
                                  started_at=now, finished_at=now + timedelta(minutes=1))
        db.session.add_all([old, newer])
        db.session.commit()

        class _BoomDelete:
            def execute(self):
                raise RuntimeError('réseau coupé')

        class _BoomFiles:
            def delete(self, fileId):
                return _BoomDelete()

        class _BoomDrive:
            def files(self):
                return _BoomFiles()

        service = BackupService(self.app)
        service.apply_retention(_BoomDrive(), 'Daily', 1)
        db.session.refresh(old)
        self.assertEqual(old.drive_file_id, 'old_id')
        self.assertIn('Rétention', old.message)

    # ── FIX 17 : repli de port borné (plus de boucle infinie) ─────────────
    def test_port_manager_bounded_fallback_raises(self):
        from desktop.port_manager import PortManager
        original_avail = PortManager.is_port_available
        original_ciento = PortManager.is_ciento_server
        PortManager.is_port_available = staticmethod(lambda port: False)
        PortManager.is_ciento_server = staticmethod(lambda port: False)
        try:
            with self.assertRaises(RuntimeError):
                PortManager().find_free_port(5005)
        finally:
            PortManager.is_port_available = original_avail
            PortManager.is_ciento_server = original_ciento

    def test_port_manager_uses_preferred_port(self):
        from desktop.port_manager import PortManager
        original_avail = PortManager.is_port_available
        PortManager.is_port_available = staticmethod(lambda port: True)
        try:
            pm = PortManager()
            self.assertEqual(pm.find_free_port(5005), 5005)
        finally:
            PortManager.is_port_available = original_avail

    def test_port_manager_fallback_within_bounded_range(self):
        from desktop.port_manager import PortManager

        def fake_avail(port):
            return port >= 10510

        original_avail = PortManager.is_port_available
        original_ciento = PortManager.is_ciento_server
        PortManager.is_port_available = staticmethod(fake_avail)
        PortManager.is_ciento_server = staticmethod(lambda port: False)
        try:
            port = PortManager().find_free_port(5005)
            self.assertEqual(port, 10510)
        finally:
            PortManager.is_port_available = original_avail
            PortManager.is_ciento_server = original_ciento

    # ── FIX 18 : journalisation idempotente ───────────────────────────────
    def test_logger_config_idempotent(self):
        import desktop.logger_config as lc
        lc.LOG_DIR = None
        lc._startup_logger = None
        lc._configured = False
        base = tempfile.mkdtemp(prefix='ciento_logs_')
        try:
            first = lc.setup_logging(base_dir=base)
            second = lc.setup_logging(base_dir=base)
            self.assertIs(first, second)
            self.assertEqual(len(logging.getLogger('startup').handlers), 1)
            self.assertEqual(len(logging.getLogger('security').handlers), 1)
        finally:
            shutil.rmtree(base, ignore_errors=True)
            lc.LOG_DIR = None
            lc._startup_logger = None
            lc._configured = False

    # ── FIX 20 : synchronisation de schéma migrate_db ─────────────────────
    def test_migrate_db_idempotent_and_syncs_indexes(self):
        from migrate_db import migrate
        migrate(self.app)
        migrate(self.app)
        insp = inspect(db.engine)
        visites_indexes = {ix['name'] for ix in insp.get_indexes('visites')}
        self.assertIn('ix_visites_client_id', visites_indexes)
        self.assertIn('ix_visites_agent_id', visites_indexes)
        self.assertIn('ix_visites_propriete_id', visites_indexes)

    def test_config_rejects_placeholder_secret_key(self):
        from config import Config as RealConfig
        self.assertNotEqual(RealConfig.SECRET_KEY,
                            'change-me-to-a-random-secret-key-at-least-32-chars')

    # ── FIX 13/16 : .env lu à côté de l'exe (plus de _MEIPASS) ────────────
    def test_startup_check_env_dir_is_base_dir_when_frozen(self):
        import sys
        import desktop.startup_checks as sc
        saved_frozen = getattr(sys, 'frozen', None)
        saved_meipass = getattr(sys, '_MEIPASS', None)
        base = tempfile.mkdtemp(prefix='ciento_checks_')
        try:
            sys.frozen = True
            sys._MEIPASS = 'C:\\fake_meipass'
            checker = sc.StartupChecker(base)
            self.assertEqual(checker._env_dir(), base)
        finally:
            if saved_frozen is None:
                sys.__dict__.pop('frozen', None)
            else:
                sys.frozen = saved_frozen
            if saved_meipass is None:
                sys.__dict__.pop('_MEIPASS', None)
            else:
                sys._MEIPASS = saved_meipass
            shutil.rmtree(base, ignore_errors=True)

    def test_startup_check_env_file_found_next_to_exe(self):
        import desktop.startup_checks as sc
        base = tempfile.mkdtemp(prefix='ciento_checks_')
        try:
            with open(os.path.join(base, '.env'), 'w', encoding='utf-8') as f:
                f.write('DB_USER=postgres\nDB_PASSWORD=12345678\n'
                        'DB_HOST=localhost\nDB_PORT=5432\n'
                        'DB_NAME=ciento_immobilier_db\nSECRET_KEY=abc\n')
            checker = sc.StartupChecker(base)
            checker._check_env_file()
            self.assertNotIn('.env file not found', checker.errors)
            self.assertEqual(checker.errors, [])
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
