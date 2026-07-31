"""
Orchestrateur des sauvegardes cloud : exports → ZIP → chiffrement AES-256 →
upload Google Drive → historique → retention → restauration.

L'execution s'effectue dans un thread de fond ; la progression est exposee
via un magasin en memoire (job_id) interroge par l'interface web (progression,
vitesse, taille, temps restant).
"""
import os
import shutil
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone
from io import BytesIO

from sqlalchemy import select

from app import db
from app.models import CloudBackupRecord, CloudBackupSchedule, CloudBackupSetting
from app.services import crypto_service
from app.services.crypto_service import CryptoError
from app.services.export_service import REPORT_GROUPS, export_csv, export_excel, export_pdf, export_sql
from app.services.google_drive_service import GoogleDriveError, GoogleDriveService

FOLDER_BY_TYPE = {
    'Daily': 'Daily',
    'Weekly': 'Weekly',
    'Monthly': 'Monthly',
    'Archive': 'Archive',
    'Manual': 'Archive',
}
MIME_ENC = 'application/octet-stream'
KEEP_JOB_AFTER_DONE = 300  # secondes avant purge du statut en memoire


class ProgressStore:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def create(self, job_id):
        job = {
            'status': 'running',
            'progress': 0,
            'message': 'Initialisation...',
            'current': 0,
            'total': 0,
            'uploaded': 0,
            'total_bytes': 0,
            'speed': 0,
            'eta': 0,
            'finished_at': None,
        }
        with self._lock:
            self._jobs[job_id] = job
        return job

    def update(self, job_id, **kwargs):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.update(kwargs)

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return {}
            return dict(job)

    def remove(self, job_id):
        with self._lock:
            self._jobs.pop(job_id, None)


def _parse_include(include_data):
    if not include_data or include_data == 'all':
        return set(REPORT_GROUPS.keys())
    return {k.strip() for k in str(include_data).split(',')
            if k.strip() in REPORT_GROUPS}


class BackupService:
    def __init__(self, app):
        self.app = app
        self.progress = ProgressStore()
        self._execution_lock = threading.Lock()

    # ── Lancement ──────────────────────────────────────────────────────────
    def run_manual_backup(self, user_name, backup_type='Manual', include_data='all'):
        job_id = f'backup_{int(time.time() * 1000)}'
        self.progress.create(job_id)
        thread = threading.Thread(
            target=self._threaded_execution,
            args=(job_id, backup_type, user_name, include_data),
            daemon=True,
        )
        thread.start()
        return job_id

    def _threaded_execution(self, job_id, backup_type, user_name, include_data):
        with self.app.app_context():
            if not self._execution_lock.acquire(blocking=False):
                self.progress.update(job_id, status='failed', progress=100,
                                     message='Une sauvegarde est déjà en cours.',
                                     finished_at=datetime.now(timezone.utc))
                return
            try:
                self._run_backup(job_id, backup_type, user_name, include_data)
            finally:
                self._execution_lock.release()

    # ── Exécution ──────────────────────────────────────────────────────────
    def _run_backup(self, job_id, backup_type, user_name, include_data):
        started = time.time()
        record = CloudBackupRecord(backup_type=backup_type, status='running',
                                   triggered_by=user_name)
        db.session.add(record)
        db.session.commit()
        record_id = record.id

        tmpdir = tempfile.mkdtemp(prefix='ciento_backup_')
        try:
            setting = CloudBackupSetting.get()
            passphrase = crypto_service.unwrap_secret(
                setting.encryption_passphrase_wrapped)
            if not passphrase:
                raise GoogleDriveError(
                    'Aucune phrase de passe de chiffrement définie dans les paramètres.')

            self.progress.update(job_id, message='Connexion à Google Drive...', progress=3)
            service = GoogleDriveService(setting)
            drive = service.build_service()
            folders = service.ensure_backup_tree(drive)
            target = FOLDER_BY_TYPE.get(backup_type, 'Archive')

            included = _parse_include(include_data)
            export_dir = os.path.join(tmpdir, 'sauvegarde')
            os.makedirs(export_dir, exist_ok=True)
            file_count = 0

            groups = [g for g in REPORT_GROUPS if g in included]
            for index, group in enumerate(groups):
                base_pct = 3 + int(37 * (index / max(len(groups), 1)))
                self.progress.update(
                    job_id, progress=base_pct,
                    message=f'Export {REPORT_GROUPS[group]["label"]}...')
                for fmt, writer in (('csv', export_csv), ('xlsx', export_excel),
                                    ('pdf', export_pdf)):
                    data = writer(group)
                    with open(os.path.join(export_dir, f'{group}.{fmt}'), 'wb') as fh:
                        fh.write(data)
                    file_count += 1

            self.progress.update(job_id, progress=40, message='Dump SQL de la base...')
            with open(os.path.join(export_dir, 'base_de_donnees.sql'), 'w',
                      encoding='utf-8') as fh:
                fh.write(export_sql())
            file_count += 1

            info_lines = [
                'CIENTO IMMOBILIER — Sauvegarde automatique',
                f'Type : {backup_type}',
                f'Date : {datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S")}',
                f'Déclenchée par : {user_name}',
                f'Données incluses : {", ".join(sorted(included))}',
                f'Chiffrement : AES-256-GCM',
            ]
            with open(os.path.join(export_dir, 'INFORMATIONS.txt'), 'w',
                      encoding='utf-8') as fh:
                fh.write('\n'.join(info_lines) + '\n')
            file_count += 1

            self.progress.update(job_id, progress=42, message='Compression des fichiers...')
            zip_name = (f'ciento_backup_{backup_type}_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.zip')
            zip_path = os.path.join(tmpdir, zip_name)
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(export_dir):
                    for name in files:
                        full = os.path.join(root, name)
                        zf.write(full, os.path.relpath(full, tmpdir))

            self.progress.update(job_id, progress=55, message='Chiffrement AES-256...')
            with open(zip_path, 'rb') as fh:
                encrypted = crypto_service.encrypt_bytes(fh.read(), passphrase)
            encrypted_path = zip_path + '.ciento'
            with open(encrypted_path, 'wb') as fh:
                fh.write(encrypted)

            def upload_cb(uploaded, total, elapsed):
                speed = uploaded / elapsed if elapsed > 0 else 0
                eta = (total - uploaded) / speed if speed > 0 else 0
                pct = 60 + int(35 * min(uploaded / total, 1))
                self.progress.update(
                    job_id, uploaded=uploaded, total_bytes=total,
                    speed=speed, eta=eta, progress=pct,
                    message=f'Téléversement {pct - 60}% ({_human_size(uploaded)} / {_human_size(total)})...')

            self.progress.update(job_id, progress=60, message='Upload vers Google Drive...')
            drive_file_id = service.upload(drive, encrypted_path,
                                           folders[target], MIME_ENC, upload_cb)

            email = None
            try:
                email = service.get_account_email(drive)
                setting.google_account_email = email
            except Exception:
                email = setting.google_account_email

            record.drive_file_id = drive_file_id
            record.drive_folder = target
            record.file_name = zip_name
            record.size_bytes = os.path.getsize(encrypted_path)
            record.file_count = file_count
            record.finished_at = datetime.now(timezone.utc)
            record.duration_seconds = time.time() - started
            record.status = 'success'
            record.account_email = email
            record.message = 'Sauvegarde téléversée et chiffrée avec succès.'
            db.session.commit()

            schedule = CloudBackupSchedule.get()
            self.apply_retention(drive, target, schedule.retention or 7)
            self.progress.update(job_id, progress=100, status='success',
                                 message='Sauvegarde terminée avec succès.',
                                 finished_at=datetime.now(timezone.utc))
        except Exception as exc:
            db.session.rollback()
            logger_message = str(exc)
            db.session.execute(
                db.update(CloudBackupRecord)
                .where(CloudBackupRecord.id == record_id)
                .values(status='failed', finished_at=datetime.now(timezone.utc),
                        duration_seconds=time.time() - started,
                        message=logger_message))
            db.session.commit()
            self.progress.update(job_id, progress=100, status='failed',
                                 message=logger_message,
                                 finished_at=datetime.now(timezone.utc))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ── Rétention ──────────────────────────────────────────────────────────
    def apply_retention(self, drive, folder_name, retention):
        if not retention or int(retention) < 1:
            return
        records = db.session.execute(
            select(CloudBackupRecord)
            .where(CloudBackupRecord.drive_folder == folder_name,
                   CloudBackupRecord.status == 'success',
                   CloudBackupRecord.drive_file_id.isnot(None),
                   CloudBackupRecord.finished_at.isnot(None))
            .order_by(CloudBackupRecord.finished_at.desc())
        ).scalars().all()
        for record in records[int(retention):]:
            try:
                drive.files().delete(fileId=record.drive_file_id).execute()
            except Exception:
                pass
            record.drive_file_id = None
            record.message = (record.message or '') + ' [Fichier supprimé par rétention]'
        db.session.commit()

    # ── Restauration ───────────────────────────────────────────────────────
    def restore_backup(self, record_id, passphrase):
        record = db.session.get(CloudBackupRecord, record_id)
        if record is None:
            raise GoogleDriveError('Sauvegarde introuvable.')
        if not record.drive_file_id:
            raise GoogleDriveError('Le fichier Drive de cette sauvegarde a été supprimé (rétention).')
        tmpdir = tempfile.mkdtemp(prefix='ciento_restore_')
        try:
            service = GoogleDriveService()
            drive = service.build_service()
            encrypted_path = os.path.join(tmpdir, 'backup.ciento')
            service.download(drive, record.drive_file_id, encrypted_path)
            with open(encrypted_path, 'rb') as fh:
                payload = fh.read()
            try:
                data = crypto_service.decrypt_bytes(payload, passphrase)
            except CryptoError as exc:
                raise GoogleDriveError(str(exc))
            with zipfile.ZipFile(BytesIO(data)) as zf:
                zf.extractall(tmpdir)
                names = zf.namelist()
            sql_name = next((n for n in names
                             if n.endswith('base_de_donnees.sql')), None)
            if not sql_name:
                raise GoogleDriveError('Archive invalide : base_de_donnees.sql absent.')
            with open(os.path.join(tmpdir, sql_name), 'r', encoding='utf-8') as fh:
                script = fh.read()
            from sqlalchemy import text
            db.session.remove()
            with db.engine.connect() as conn:
                conn = conn.execution_options(isolation_level='AUTOCOMMIT')
                execute_sql_script(conn, script)
            db.session.remove()
            return record.file_name or record.drive_file_id
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ── Divers ─────────────────────────────────────────────────────────────
    def get_job_status(self, job_id):
        job = self.progress.get(job_id)
        if not job:
            return None
        if job.get('status') in ('success', 'failed') and job.get('finished_at'):
            if (datetime.now(timezone.utc) - job['finished_at']).total_seconds() > KEEP_JOB_AFTER_DONE:
                self.progress.remove(job_id)
                return None
        return job


def execute_sql_script(conn, script):
    """Execute un script SQL multi-instructions (BEGIN/COMMIT inclus).

    sqlite3 n'autorise qu'une seule instruction par execute() ; psycopg2
    (PostgreSQL) en accepte plusieurs. On adapte via la connexion DBAPI.
    """
    raw = conn.connection.driver_connection
    if db.engine.dialect.name == 'sqlite':
        raw.executescript(script)
    else:
        cursor = raw.cursor()
        cursor.execute(script)


def _human_size(num):
    for unit in ('o', 'Ko', 'Mo', 'Go', 'To'):
        if num < 1024:
            return f'{num:.1f} {unit}'
        num /= 1024
    return f'{num:.1f} To'
