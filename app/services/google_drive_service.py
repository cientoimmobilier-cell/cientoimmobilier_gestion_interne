"""
Service Google Drive du module Sauvegarde Cloud.

OAuth 2.0 uniquement (jamais de mot de passe Google). Le jeton d'acces, le
refresh token et les identifiants OAuth client sont stockes chiffres en
AES-256 dans la table cloud_backup_settings.
"""
import json
import os
import time

from app import db
from app.models import CloudBackupSetting
from app.services.crypto_service import unwrap_secret, wrap_secret

SCOPES = ['https://www.googleapis.com/auth/drive.file']
ROOT_NAME = 'CIENTO-IMMOBILIER-BACKUPS'
FOLDER_NAMES = ['Daily', 'Weekly', 'Monthly', 'Archive']
MIME_OCTET = 'application/octet-stream'


class GoogleDriveError(Exception):
    pass


class GoogleDriveService:
    """Enveloppe l'API Drive v3 et le flux OAuth2. Testable via injection."""

    def __init__(self, setting=None):
        self.setting = setting if setting is not None else CloudBackupSetting.get()

    # ── État ───────────────────────────────────────────────────────────────
    def is_configured(self):
        return bool(self.setting.google_client_id_wrapped
                    and self.setting.google_client_secret_wrapped)

    def is_connected(self):
        return bool(self.setting.token_encrypted)

    # ── OAuth2 ─────────────────────────────────────────────────────────────
    def _client_credentials(self):
        if not self.is_configured():
            raise GoogleDriveError(
                'Identifiants Google absents. Configurez le client_id et le '
                'client_secret avant la connexion.'
            )
        return (
            unwrap_secret(self.setting.google_client_id_wrapped),
            unwrap_secret(self.setting.google_client_secret_wrapped),
        )

    def _build_flow(self, redirect_uri):
        from google_auth_oauthlib.flow import Flow
        client_id, client_secret = self._client_credentials()
        flow = Flow.from_client_config(
            client_config={
                'web': {
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                    'token_uri': 'https://oauth2.googleapis.com/token',
                    'redirect_uris': [redirect_uri],
                }
            },
            scopes=SCOPES,
        )
        flow.redirect_uri = redirect_uri
        return flow

    def authorization_url(self, redirect_uri):
        flow = self._build_flow(redirect_uri)
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
        )
        return auth_url, state

    def exchange_code(self, code, redirect_uri):
        flow = self._build_flow(redirect_uri)
        flow.fetch_token(code=code)
        self._store_credentials(flow.credentials)

    def _store_credentials(self, credentials):
        data = {
            'token': credentials.token,
            'refresh_token': getattr(credentials, 'refresh_token', None),
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes,
        }
        self.setting.token_encrypted = wrap_secret(json.dumps(data))
        db.session.commit()

    def get_credentials(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        if not self.is_connected():
            raise GoogleDriveError('Aucun compte Google connecté.')
        info = json.loads(unwrap_secret(self.setting.token_encrypted))
        credentials = Credentials.from_authorized_user_info(info, scopes=SCOPES)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._store_credentials(credentials)
        return credentials

    def clear_credentials(self):
        self.setting.token_encrypted = None
        self.setting.google_account_email = None
        db.session.commit()

    def set_credentials(self, client_id, client_secret):
        self.setting.google_client_id_wrapped = wrap_secret(client_id)
        self.setting.google_client_secret_wrapped = wrap_secret(client_secret)
        db.session.commit()

    # ── API Drive ──────────────────────────────────────────────────────────
    def build_service(self, credentials=None):
        from googleapiclient.discovery import build
        credentials = credentials or self.get_credentials()
        return build('drive', 'v3', credentials=credentials,
                     cache_discovery=False)

    def get_account_email(self, service=None):
        service = service or self.build_service()
        try:
            about = service.about().get(fields='user(emailAddress)').execute()
            return about['user']['emailAddress']
        except Exception:
            return self.setting.google_account_email or 'Compte Google'

    def get_storage_info(self, service=None):
        service = service or self.build_service()
        about = service.about().get(fields='storageQuota(limit,usage)').execute()
        quota = about.get('storageQuota', {})
        try:
            limit = int(quota.get('limit', 0))
            usage = int(quota.get('usage', 0))
        except (TypeError, ValueError):
            limit = usage = 0
        return {'limit': limit, 'usage': usage}

    def _ensure_folder(self, service, name, parent_id, cached_id):
        if cached_id:
            return cached_id
        query = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        )
        if parent_id:
            query += f" and '{parent_id}' in parents"
        existing = service.files().list(
            q=query, fields='files(id,name)', pageSize=5).execute()
        files = existing.get('files', [])
        if files:
            return files[0]['id']
        body = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
        if parent_id:
            body['parents'] = [parent_id]
        created = service.files().create(body=body, fields='id').execute()
        return created['id']

    def ensure_backup_tree(self, service=None):
        """Garantit le dossier CIENTO-IMMOBILIER-BACKUPS/{Daily|...|Archive}."""
        service = service or self.build_service()
        root = self._ensure_folder(service, ROOT_NAME, None,
                                   self.setting.drive_root_id)
        self.setting.drive_root_id = root
        folders = {}
        for name in FOLDER_NAMES:
            attr = f'drive_{name.lower()}_id'
            folder_id = self._ensure_folder(service, name, root,
                                            getattr(self.setting, attr))
            setattr(self.setting, attr, folder_id)
            folders[name] = folder_id
        db.session.commit()
        return folders

    def upload(self, service, path, folder_id, mime=MIME_OCTET, progress_cb=None):
        from googleapiclient.http import MediaFileUpload
        total = os.path.getsize(path)
        media = MediaFileUpload(path, mimetype=mime, resumable=True, chunksize=262144)
        request = service.files().create(
            body={'name': os.path.basename(path), 'parents': [folder_id]},
            media_body=media,
            fields='id',
        )
        uploaded = 0
        started = time.time()
        response = None
        while response is None:
            status, response = request.next_chunk(num_retries=3)
            if status and progress_cb:
                progress_cb(int(status.resumable_progress), total, time.time() - started)
        if progress_cb:
            progress_cb(total, total, time.time() - started)
        return response['id']

    def list_files(self, service, folder_id, page_size=100):
        items = []
        page_token = None
        while True:
            result = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                pageSize=page_size,
                fields='nextPageToken, files(id,name,size,modifiedTime,createdTime)',
                pageToken=page_token,
            ).execute()
            items.extend(result.get('files', []))
            page_token = result.get('nextPageToken')
            if not page_token:
                break
        return items

    def download(self, service, file_id, dest_path):
        from googleapiclient.http import MediaIoBaseDownload
        from io import FileIO
        request = service.files().get_media(fileId=file_id)
        with FileIO(dest_path, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request, chunksize=262144)
            done = False
            while not done:
                _, done = downloader.next_chunk(num_retries=3)
        return dest_path

    def delete(self, service, file_id):
        service.files().delete(fileId=file_id).execute()
