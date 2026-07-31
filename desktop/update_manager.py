import os
import json
import logging
import urllib.request
import urllib.error
import subprocess
import shutil
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)


class UpdateManager:
    VERSION = '1.0.0'
    UPDATE_URL = 'https://api.ciento-immobilier.com/updates/check'
    UPDATE_DOWNLOAD_URL = 'https://api.ciento-immobilier.com/updates/download'

    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._update_info = None

    def check_for_updates(self):
        try:
            req = urllib.request.Request(
                self.UPDATE_URL,
                data=json.dumps({'version': self.VERSION}).encode(),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if data.get('update_available'):
                    self._update_info = data
                    logger.info(f'Update available: v{data["version"]}')
                    return data
                logger.info('No updates available')
                return None
        except Exception as e:
            logger.warning(f'Update check failed: {e}')
            return None

    @property
    def update_available(self):
        return self._update_info is not None

    def download_update(self, progress_callback=None):
        if not self._update_info:
            return {'success': False, 'error': 'No update info available'}

        try:
            download_url = self._update_info.get('download_url', self.UPDATE_DOWNLOAD_URL)
            temp_dir = tempfile.mkdtemp(prefix='ciento_update_')
            installer_path = os.path.join(temp_dir, 'CientoImmobilier_Setup.exe')

            logger.info(f'Downloading update from {download_url}')

            def report(block_count, block_size, total_size):
                if progress_callback and total_size > 0:
                    pct = min(100, int(block_count * block_size * 100 / total_size))
                    progress_callback(pct)

            urllib.request.urlretrieve(download_url, installer_path, reporthook=report)
            size = os.path.getsize(installer_path)
            logger.info(f'Update downloaded ({size} bytes) to {installer_path}')

            return {
                'success': True,
                'installer_path': installer_path,
                'version': self._update_info['version'],
                'changelog': self._update_info.get('changelog', '')
            }
        except Exception as e:
            logger.error(f'Update download failed: {e}')
            return {'success': False, 'error': str(e)}

    @staticmethod
    def install_update(installer_path):
        try:
            logger.info(f'Launching installer: {installer_path}')
            subprocess.Popen([installer_path, '/SILENT', '/CLOSEAPPLICATIONS'],
                             shell=True)
            return {'success': True}
        except Exception as e:
            logger.error(f'Failed to launch installer: {e}')
            return {'success': False, 'error': str(e)}
