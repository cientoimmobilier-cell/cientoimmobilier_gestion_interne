"""
Routes du module Sauvegarde Cloud Google Drive.

Accessible aux Administrateurs et Directeurs uniquement. Le module fournit :
connexion OAuth2 Google, sauvegarde manuelle avec progression en temps reel,
planification, historique, telechargement et restauration des archives
chiffrees AES-256.
"""
import logging
import os
import shutil
import tempfile

from flask import (Blueprint, after_this_request, current_app, flash,
                   jsonify, redirect, render_template, request, send_file,
                   session, url_for)
from flask_login import current_user, login_required
from sqlalchemy import select

from app import db
from app.models import (CloudBackupRecord, CloudBackupSchedule,
                        CloudBackupSetting)
from app.services import crypto_service
from app.services.backup_service import FOLDER_BY_TYPE
from app.services.google_drive_service import GoogleDriveError, GoogleDriveService
from app.services.export_service import REPORT_GROUPS
from app.utils.helpers import role_required

logger = logging.getLogger(__name__)

cloud_backup_bp = Blueprint('cloud_backup', __name__,
                            url_prefix='/parametres/sauvegarde-cloud')

PASSPHRASE_MIN = crypto_service.MIN_PASSPHRASE_LENGTH


def _redirect_uri():
    return url_for('cloud_backup.callback', _external=True)


def _backup_service():
    app = current_app._get_current_object()
    service = app.extensions.get('backup_service')
    if service is None:
        from app.services.backup_service import BackupService
        service = BackupService(app)
        app.extensions['backup_service'] = service
    return service


@cloud_backup_bp.route('/')
@login_required
@role_required('Administrateur', 'Directeur')
def index():
    setting = CloudBackupSetting.get()
    schedule = CloudBackupSchedule.get()
    service = GoogleDriveService(setting)

    quota = None
    if service.is_connected():
        try:
            quota = service.get_storage_info()
        except Exception:
            quota = None

    recent = db.session.execute(
        select(CloudBackupRecord).order_by(CloudBackupRecord.started_at.desc())
        .limit(5)).scalars().all()

    return render_template(
        'cloud_backup/index.html',
        setting=setting, schedule=schedule, service=service,
        quota=quota, recent=recent, groups=REPORT_GROUPS,
        passphrase_min=PASSPHRASE_MIN,
    )


# ── Connexion Google ────────────────────────────────────────────────────────
@cloud_backup_bp.route('/connexion')
@login_required
@role_required('Administrateur', 'Directeur')
def connect():
    service = GoogleDriveService()
    if not service.is_configured():
        flash('Configurez d\'abord le client_id et le client_secret Google.', 'warning')
        return redirect(url_for('cloud_backup.index'))
    try:
        auth_url, state = service.authorization_url(_redirect_uri())
        session['cloud_oauth_state'] = state
        return redirect(auth_url)
    except Exception as exc:
        logger.error('[CLOUD] Erreur connexion Google: %s', exc)
        flash('Impossible de démarrer la connexion Google.', 'danger')
        return redirect(url_for('cloud_backup.index'))


@cloud_backup_bp.route('/callback')
@login_required
@role_required('Administrateur', 'Directeur')
def callback():
    state = request.args.get('state')
    code = request.args.get('code')
    error = request.args.get('error')
    if error:
        flash(f'Connexion Google annulée ou refusée : {error}', 'danger')
        return redirect(url_for('cloud_backup.index'))
    if not code or state != session.pop('cloud_oauth_state', None):
        flash('Connexion Google invalide (état de session incorrect).', 'danger')
        return redirect(url_for('cloud_backup.index'))
    try:
        service = GoogleDriveService()
        service.exchange_code(code, _redirect_uri())
        flash('Compte Google connecté avec succès.', 'success')
    except Exception as exc:
        logger.error('[CLOUD] Erreur échange code OAuth: %s', exc)
        db.session.rollback()
        flash('Échec de la connexion Google. Réessayez.', 'danger')
    return redirect(url_for('cloud_backup.index'))


@cloud_backup_bp.route('/deconnexion', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def disconnect():
    GoogleDriveService().clear_credentials()
    flash('Compte Google déconnecté.', 'info')
    return redirect(url_for('cloud_backup.index'))


@cloud_backup_bp.route('/identifiants', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def save_credentials():
    client_id = request.form.get('google_client_id', '').strip()
    client_secret = request.form.get('google_client_secret', '').strip()
    if not client_id or not client_secret:
        flash('Le client_id et le client_secret sont obligatoires.', 'danger')
        return redirect(url_for('cloud_backup.index'))
    try:
        GoogleDriveService().set_credentials(client_id, client_secret)
        flash('Identifiants Google enregistrés (chiffrés).', 'success')
    except Exception as exc:
        logger.error('[CLOUD] Erreur enregistrement identifiants: %s', exc)
        db.session.rollback()
        flash('Erreur lors de l\'enregistrement des identifiants.', 'danger')
    return redirect(url_for('cloud_backup.index'))


@cloud_backup_bp.route('/suggestion-cle')
@login_required
@role_required('Administrateur', 'Directeur')
def suggest_passphrase():
    return jsonify({'passphrase': crypto_service.generate_passphrase()})


# ── Phrase de passe de chiffrement ──────────────────────────────────────────
@cloud_backup_bp.route('/cle', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def save_passphrase():
    passphrase = request.form.get('passphrase', '')
    confirmation = request.form.get('confirmation', '')
    if len(passphrase) < PASSPHRASE_MIN:
        flash(f'La phrase de passe doit contenir au moins {PASSPHRASE_MIN} caractères.', 'danger')
        return redirect(url_for('cloud_backup.index'))
    if passphrase != confirmation:
        flash('La confirmation de la phrase de passe ne correspond pas.', 'danger')
        return redirect(url_for('cloud_backup.index'))
    setting = CloudBackupSetting.get()
    setting.encryption_passphrase_wrapped = crypto_service.wrap_secret(passphrase)
    setting.passphrase_set_at = db.func.now()
    db.session.commit()
    flash('Phrase de passe de chiffrement enregistrée.', 'success')
    return redirect(url_for('cloud_backup.index'))


# ── Planification ───────────────────────────────────────────────────────────
@cloud_backup_bp.route('/planification', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def save_schedule():
    from app.services.scheduler_service import compute_next_run
    schedule = CloudBackupSchedule.get()
    schedule.enabled = 'enabled' in request.form
    schedule.frequency = request.form.get('frequency', 'daily')
    schedule.hour = max(0, min(23, int(request.form.get('hour', 2) or 2)))
    schedule.minute = max(0, min(59, int(request.form.get('minute', 0) or 0)))
    schedule.day_of_week = max(0, min(6, int(request.form.get('day_of_week', 1) or 1)))
    schedule.day_of_month = max(1, min(28, int(request.form.get('day_of_month', 1) or 1)))
    schedule.retention = max(1, min(365, int(request.form.get('retention', 7) or 7)))
    include = [k for k in request.form.getlist('include_data')
               if k in REPORT_GROUPS]
    schedule.include_data = ','.join(include) if include else 'all'
    schedule.next_run_at = compute_next_run(
        schedule.frequency, schedule.hour, schedule.minute,
        schedule.day_of_week, schedule.day_of_month)
    db.session.commit()
    flash('Planification des sauvegardes mise à jour.', 'success')
    return redirect(url_for('cloud_backup.index'))


# ── Sauvegarde manuelle + progression ───────────────────────────────────────
@cloud_backup_bp.route('/backup', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def start_backup():
    setting = CloudBackupSetting.get()
    if not setting.encryption_passphrase_wrapped:
        flash('Définissez d\'abord la phrase de passe de chiffrement.', 'danger')
        return redirect(url_for('cloud_backup.index'))
    service = GoogleDriveService(setting)
    if not service.is_connected():
        flash('Connectez d\'abord votre compte Google.', 'danger')
        return redirect(url_for('cloud_backup.index'))

    backup_type = request.form.get('backup_type', 'Manual')
    if backup_type not in FOLDER_BY_TYPE:
        backup_type = 'Manual'
    include = [k for k in request.form.getlist('include_data')
               if k in REPORT_GROUPS]
    include_data = ','.join(include) if include else 'all'
    user_name = f"{current_user.prenom} {current_user.nom}".strip() or current_user.email

    job_id = _backup_service().run_manual_backup(
        user_name, backup_type, include_data)
    return redirect(url_for('cloud_backup.progress', job_id=job_id))


@cloud_backup_bp.route('/progression/<job_id>')
@login_required
@role_required('Administrateur', 'Directeur')
def progress(job_id):
    status = _backup_service().get_job_status(job_id)
    if status is None:
        flash('Sauvegarde introuvable ou expirée.', 'warning')
        return redirect(url_for('cloud_backup.index'))
    return render_template('cloud_backup/progress.html', job_id=job_id,
                           status=status)


@cloud_backup_bp.route('/statut/<job_id>')
@login_required
@role_required('Administrateur', 'Directeur')
def status(job_id):
    status = _backup_service().get_job_status(job_id)
    if status is None:
        return jsonify({'status': 'not_found'}), 404
    payload = dict(status)
    if payload.get('finished_at'):
        payload['finished_at'] = payload['finished_at'].isoformat()
    return jsonify(payload)


# ── Liste / historique ──────────────────────────────────────────────────────
@cloud_backup_bp.route('/sauvegardes')
@login_required
@role_required('Administrateur', 'Directeur')
def backups():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    backup_type = request.args.get('type', '').strip()
    status = request.args.get('statut', '').strip()

    stmt = select(CloudBackupRecord)
    if backup_type in FOLDER_BY_TYPE:
        stmt = stmt.where(CloudBackupRecord.backup_type == backup_type)
    if status in ('success', 'failed', 'running'):
        stmt = stmt.where(CloudBackupRecord.status == status)
    stmt = stmt.order_by(CloudBackupRecord.started_at.desc())

    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)

    setting = CloudBackupSetting.get()
    service = GoogleDriveService(setting)
    quota = None
    account_email = None
    if service.is_connected():
        try:
            quota = service.get_storage_info()
            account_email = setting.google_account_email
        except Exception:
            quota = None

    return render_template(
        'cloud_backup/backups.html',
        records=pagination.items, pagination=pagination,
        backup_type=backup_type, status_filter=status,
        quota=quota, account_email=account_email,
        types=list(FOLDER_BY_TYPE.keys()),
    )


@cloud_backup_bp.route('/historique')
@login_required
@role_required('Administrateur', 'Directeur')
def history():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    backup_type = request.args.get('type', '').strip()
    status = request.args.get('statut', '').strip()

    stmt = select(CloudBackupRecord)
    if backup_type in FOLDER_BY_TYPE:
        stmt = stmt.where(CloudBackupRecord.backup_type == backup_type)
    if status in ('success', 'failed', 'running'):
        stmt = stmt.where(CloudBackupRecord.status == status)
    stmt = stmt.order_by(CloudBackupRecord.started_at.desc())

    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    return render_template(
        'cloud_backup/history.html',
        records=pagination.items, pagination=pagination,
        backup_type=backup_type, status_filter=status,
        types=list(FOLDER_BY_TYPE.keys()),
    )


# ── Téléchargement / restauration / suppression ─────────────────────────────
@cloud_backup_bp.route('/telecharger/<int:record_id>')
@login_required
@role_required('Administrateur', 'Directeur')
def download(record_id):
    record = db.session.get(CloudBackupRecord, record_id)
    if record is None or not record.drive_file_id:
        flash('Fichier de sauvegarde introuvable.', 'danger')
        return redirect(url_for('cloud_backup.backups'))
    tmpdir = tempfile.mkdtemp(prefix='ciento_dl_')
    dest = os.path.join(tmpdir, record.file_name + '.ciento')
    try:
        GoogleDriveService().download(GoogleDriveService().build_service(),
                                      record.drive_file_id, dest)
    except Exception as exc:
        logger.error('[CLOUD] Erreur téléchargement %s: %s', record_id, exc)
        flash('Échec du téléchargement depuis Google Drive.', 'danger')
        return redirect(url_for('cloud_backup.backups'))

    @after_this_request
    def _cleanup(response):
        shutil.rmtree(tmpdir, ignore_errors=True)
        return response

    return send_file(dest, as_attachment=True,
                     download_name=record.file_name + '.ciento')


@cloud_backup_bp.route('/restaurer/<int:record_id>', methods=['GET', 'POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def restore(record_id):
    record = db.session.get(CloudBackupRecord, record_id)
    if record is None:
        flash('Sauvegarde introuvable.', 'danger')
        return redirect(url_for('cloud_backup.backups'))
    if request.method == 'GET':
        return render_template('cloud_backup/restore.html', record=record)
    passphrase = request.form.get('passphrase', '')
    if not passphrase:
        flash('La phrase de passe est obligatoire pour restaurer.', 'danger')
        return render_template('cloud_backup/restore.html', record=record)
    if 'confirm_restore' not in request.form:
        flash('Vous devez confirmer la restauration.', 'danger')
        return render_template('cloud_backup/restore.html', record=record)
    try:
        name = _backup_service().restore_backup(record.id, passphrase)
        flash(f'Restauration de « {name} » réussie.', 'success')
    except GoogleDriveError as exc:
        flash(str(exc), 'danger')
        return render_template('cloud_backup/restore.html', record=record)
    except Exception as exc:
        logger.error('[CLOUD] Erreur restauration %s: %s', record_id, exc)
        db.session.rollback()
        flash('Erreur lors de la restauration de la base de données.', 'danger')
    return redirect(url_for('cloud_backup.backups'))


@cloud_backup_bp.route('/supprimer/<int:record_id>', methods=['POST'])
@login_required
@role_required('Administrateur', 'Directeur')
def delete(record_id):
    record = db.session.get(CloudBackupRecord, record_id)
    if record is None:
        flash('Sauvegarde introuvable.', 'danger')
        return redirect(url_for('cloud_backup.backups'))
    if record.drive_file_id:
        try:
            GoogleDriveService().delete(GoogleDriveService().build_service(),
                                        record.drive_file_id)
        except Exception as exc:
            logger.error('[CLOUD] Erreur suppression Drive %s: %s', record_id, exc)
    db.session.delete(record)
    db.session.commit()
    flash('Sauvegarde supprimée.', 'success')
    return redirect(url_for('cloud_backup.backups'))
