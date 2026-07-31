import os
import io
import zipfile
import logging
import threading
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class BackupManager:
    def __init__(self, base_dir=None, backup_dir=None):
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.backup_dir = backup_dir or os.path.join(self.base_dir, 'backups')
        self._history = []
        self._timer = None
        self._running = False
        self._auto_enabled = False
        os.makedirs(self.backup_dir, exist_ok=True)
        self._load_history()

    def _load_history(self):
        self._history = []
        if os.path.isdir(self.backup_dir):
            for f in sorted(os.listdir(self.backup_dir), reverse=True):
                if f.endswith('.zip') and f.startswith('ciento_backup_'):
                    path = os.path.join(self.backup_dir, f)
                    size = os.path.getsize(path)
                    ts_str = f.replace('ciento_backup_', '').replace('.zip', '')
                    try:
                        ts = datetime.strptime(ts_str, '%Y%m%d_%H%M%S')
                    except ValueError:
                        ts = datetime.fromtimestamp(os.path.getmtime(path))
                    self._history.append({
                        'filename': f, 'path': path,
                        'size': size, 'size_mb': round(size / (1024 * 1024), 2),
                        'date': ts, 'timestamp': ts.strftime('%d/%m/%Y %H:%M:%S')
                    })

    @property
    def history(self):
        return self._history

    def create_backup(self):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'ciento_backup_{timestamp}.zip'
        zip_path = os.path.join(self.backup_dir, filename)

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                self._zip_directory(zf, os.path.join(self.base_dir, 'app'), 'app/')
                uploads = os.path.join(self.base_dir, 'app', 'static', 'uploads')
                if os.path.isdir(uploads):
                    self._zip_directory(zf, uploads, 'uploads/')
                env_path = os.path.join(self.base_dir, '.env')
                if os.path.exists(env_path):
                    zf.write(env_path, '.env')

                export_dir = os.path.join(self.base_dir, 'exports')
                if os.path.isdir(export_dir):
                    self._zip_directory(zf, export_dir, 'exports/')

            size_mb = round(os.path.getsize(zip_path) / (1024 * 1024), 2)
            self._load_history()
            logger.info(f'Backup created: {filename} ({size_mb} MB)')
            return {'success': True, 'filename': filename, 'size_mb': size_mb}
        except Exception as e:
            logger.error(f'Backup failed: {e}')
            return {'success': False, 'error': str(e)}

    def _zip_directory(self, zf, dir_path, arc_prefix):
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                arc_name = arc_prefix + os.path.relpath(file_path, dir_path)
                try:
                    zf.write(file_path, arc_name)
                except Exception as e:
                    logger.warning(f'Skipping {file_path}: {e}')

    def restore_backup(self, filename):
        zip_path = os.path.join(self.backup_dir, filename)
        if not os.path.exists(zip_path):
            return {'success': False, 'error': 'Backup file not found'}

        restore_dir = os.path.join(self.base_dir, 'temp', 'restore')
        os.makedirs(restore_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(restore_dir)
            logger.info(f'Backup extracted to {restore_dir}')
            return {'success': True, 'restore_dir': restore_dir}
        except Exception as e:
            logger.error(f'Restore failed: {e}')
            return {'success': False, 'error': str(e)}

    def delete_backup(self, filename):
        zip_path = os.path.join(self.backup_dir, filename)
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
                self._load_history()
                return {'success': True}
            return {'success': False, 'error': 'File not found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def enable_auto_backup(self, interval_hours=24):
        self._auto_enabled = True
        self._schedule_next(interval_hours)

    def disable_auto_backup(self):
        self._auto_enabled = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _schedule_next(self, interval_hours):
        if not self._auto_enabled:
            return
        self._timer = threading.Timer(interval_hours * 3600, self._auto_backup_job, [interval_hours])
        self._timer.daemon = True
        self._timer.start()

    def _auto_backup_job(self, interval_hours):
        try:
            result = self.create_backup()
            if result['success']:
                logger.info(f'Auto-backup completed: {result["filename"]}')
        except Exception as e:
            logger.error(f'Auto-backup failed: {e}')
        self._schedule_next(interval_hours)
