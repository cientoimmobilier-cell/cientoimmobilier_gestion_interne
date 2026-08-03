"""
Validation bout-en-bout du cycle sauvegarde → restauration sur PostgreSQL réel.

Scénario (non destructif pour la base de production) :
  1. Sauvegarde complète de la base réelle via BackupService (Drive simulé en
     mémoire) → artefact chiffré identique à celui poussé sur Google Drive.
  2. Inspection de l'archive : manifest v2 valide, checksum cohérent, aucune
     clé (phrase de passe, jeton OAuth, identifiants Google) dans le clair.
  3. Création d'une base vierge `ciento_validation_<ts>`.
  4. Restauration de l'archive dans la base vierge (config cloud + uploads
     exclus du Drive : entièrement locales).
  5. Comparaison production vs restauré : nombre de lignes et contenu complet
     de chaque table, intégrité des clés étrangères, uploads octet pour octet,
     état de cloud_backup_settings (secrets NULL, phrase de passe ré-injectée).

Le script s'exécute uniquement contre le PostgreSQL local. La sauvegarde
générée n'est jamais envoyée vers Google Drive.
"""
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from io import BytesIO

import psycopg2
from sqlalchemy import select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import db, create_app
from app.models import CloudBackupRecord, CloudBackupSetting
from app.services import backup_service, crypto_service
from app.services.backup_manifest import MANIFEST_MEMBER, SQL_MEMBER, load_manifest, validate_manifest
from app.services.export_service import SECRET_COLUMNS
from config import Config


class ValidationConfig(Config):
    TESTING = True


class LocalDriveService:
    """Simulation de Google Drive en mémoire (upload + download)."""
    store = {}

    def __init__(self, setting=None):
        pass

    def build_service(self):
        return self

    def ensure_backup_tree(self, drive=None):
        return {'Daily': 'd', 'Weekly': 'w', 'Monthly': 'm', 'Archive': 'a'}

    def upload(self, drive, path, folder_id, mime, progress_cb=None):
        with open(path, 'rb') as fh:
            data = fh.read()
        file_id = f'local_{len(self.store) + 1}'
        self.store[file_id] = data
        if progress_cb:
            progress_cb(len(data), len(data), 0.5)
        return file_id

    def download(self, drive, file_id, dest_path):
        with open(dest_path, 'wb') as fh:
            fh.write(self.store[file_id])

    def get_account_email(self, drive=None):
        raise backup_service.GoogleDriveError('Drive local de validation')

    def files(self):
        class _Noop:
            def delete(self, fileId=None):
                return self

            def execute(self):
                return None
        return _Noop()


RESULTS = []


def check(label, ok, detail=''):
    RESULTS.append((label, bool(ok), detail))
    status = 'PASS' if ok else 'FAIL'
    print(f'  [{status}] {label}' + (f' — {detail}' if detail else ''))


def canon_value(value):
    if value is None:
        return 'NULL'
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    if isinstance(value, (int, float, bool)):
        return repr(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode('ascii')
    if isinstance(value, str):
        return value
    return str(value)


def fetch_all(conn, table):
    # Sélection explicite dans l'ordre des métadonnées : l'ordre physique des
    # colonnes peut différer (colonnes ajoutées par ALTER TABLE), ce qui
    # fausserait une comparaison basée sur SELECT *.
    cols = [c.name for c in db.metadata.tables[table].columns]
    cur = conn.cursor()
    cur.execute(f'SELECT {", ".join(cols)} FROM {table}')
    rows = [tuple(canon_value(v) for v in row) for row in cur.fetchall()]
    cur.close()
    return sorted(rows)


def snapshot(conn):
    return {t.name: fetch_all(conn, t.name) for t in db.metadata.sorted_tables}


def orphan_check(conn, table_name):
    cur = conn.cursor()
    cur.execute("""
        SELECT c.conname, c.conrelid::regclass::text, c.confrelid::regclass::text,
               c.conkey, c.confkey
        FROM pg_constraint c
        JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE c.contype = 'f' AND n.nspname = 'public'
        ORDER BY c.conrelid::regclass::text, c.conname
    """)
    fks = cur.fetchall()
    cur.close()
    orphans = []
    checked = 0
    for conname, child, parent, conkey, confkey in fks:
        child_cols = _attnums_to_names(conn, child, conkey)
        parent_cols = _attnums_to_names(conn, parent, confkey)
        joins = ' AND '.join(
            f'c.{cc} = p.{pc}' for cc, pc in zip(child_cols, parent_cols))
        non_null = ' OR '.join(f'c.{cc} IS NOT NULL' for cc in child_cols)
        sql = (f'SELECT c.* FROM {child} c LEFT JOIN {parent} p ON {joins} '
               f'WHERE ({non_null}) AND p.{parent_cols[0]} IS NULL')
        cur = conn.cursor()
        cur.execute(sql)
        bad = cur.fetchall()
        cur.close()
        checked += 1
        if bad:
            orphans.append((conname, child, len(bad)))
    return checked, orphans


def _attnums_to_names(conn, table, attnums):
    cur = conn.cursor()
    cur.execute(
        'SELECT attname FROM pg_attribute WHERE attrelid = %s::regclass '
        'AND attnum = ANY(%s) ORDER BY array_position(%s, attnum)',
        (table, list(attnums), list(attnums)))
    names = [r[0] for r in cur.fetchall()]
    cur.close()
    return names


def main():
    app = create_app(ValidationConfig)
    backup_service.GoogleDriveService = LocalDriveService

    # ── 0. Pré-conditions ────────────────────────────────────────────────────
    with app.app_context():
        setting = CloudBackupSetting.get()
        passphrase = crypto_service.unwrap_secret(setting.encryption_passphrase_wrapped)
        if not passphrase:
            print('FAIL: aucune phrase de passe dans la base de production.')
            return 1
        wrapped_passphrase = setting.encryption_passphrase_wrapped
        wrapped_client_secret = setting.google_client_secret_wrapped
        wrapped_token = setting.token_encrypted
        original_email = setting.google_account_email

    print(f'Passphrase : {len(passphrase)} caractères, email Google : {original_email}')
    print('Étape 1 — Sauvegarde complète (Drive simulé en mémoire)...')

    with app.app_context():
        # Aucun effet de bord sur l'historique réel ni sur la config.
        backup_service.BackupService.apply_retention = lambda self, drive, folder, retention: None
        job = app.extensions.get('backup_service')
        if job is None:
            job = backup_service.BackupService(app)
            app.extensions['backup_service'] = job
        # Exécution SYNCHRONE de la pipeline complète. _run_backup crée son
        # propre enregistrement : on le relit après coup.
        job._run_backup(f'validation_{int(time.time() * 1000)}',
                        'Manual', 'Validation automatique', 'all')
        vrec = db.session.execute(
            select(CloudBackupRecord)
            .where(CloudBackupRecord.triggered_by == 'Validation automatique')
            .order_by(CloudBackupRecord.id.desc())
        ).scalars().first()
        if vrec is None or vrec.status != 'success':
            detail = vrec.message if vrec else 'aucun enregistrement créé'
            print(f'FAIL: la sauvegarde a échoué : {detail}')
            return 1
        archive_file_id = vrec.drive_file_id
        validation_rec_id = vrec.id
        print(f'  Sauvegarde OK : {vrec.file_name}, {vrec.file_count} fichiers, '
              f'{vrec.size_bytes} octets chiffrés.')

        # ── 2. Inspection de l'archive ─────────────────────────────────────────
        print('Étape 2 — Inspection de l’archive (manifest, checksum, secrets)...')
        payload = LocalDriveService.store[archive_file_id]
        data = crypto_service.decrypt_bytes(payload, passphrase)
        check('Déchiffrement de l’archive avec la phrase de passe', data is not None)
        zf = zipfile.ZipFile(BytesIO(data))
        names = zf.namelist()
        check('manifest.json présent', any(n.endswith(MANIFEST_MEMBER) for n in names))
        check('base_de_donnees.sql présent', any(n.endswith(SQL_MEMBER) for n in names))
        check('INFORMATIONS.txt présent', any(n.endswith('INFORMATIONS.txt') for n in names))

        sql_member = next(n for n in names if n.endswith(SQL_MEMBER))
        manifest_member = next(n for n in names if n.endswith(MANIFEST_MEMBER))
        sql_bytes = zf.read(sql_member)
        manifest = load_manifest(zf.read(manifest_member))
        try:
            validate_manifest(manifest, sql_bytes)
            check('Manifest valide (format, schéma, checksum)', True)
        except Exception as exc:
            check(f'Manifest valide (format, schéma, checksum) — {exc}', False)
        check(f'Format versionné : {manifest.get("format_version")}',
              manifest.get('format_version') == 2)
        db_info = manifest.get('database') or {}
        check(f'{len(db_info.get("tables", []))} tables dans le manifest',
              len(db_info.get('tables', [])) == len(db.metadata.sorted_tables))

        # Aucun secret dans le clair de l'archive (texte + dump SQL).
        archive_text = data.decode('utf-8', errors='replace')
        for label, secret in (
                ('phrase de passe', wrapped_passphrase),
                ('client_secret Google', wrapped_client_secret),
                ('jeton OAuth', wrapped_token),
                ('SECRET_KEY', os.environ.get('SECRET_KEY', '')),
                ('DB_PASSWORD', os.environ.get('DB_PASSWORD', '')),
        ):
            if not secret:
                continue
            check(f'Secret {label} absent du contenu de l’archive',
                  secret not in archive_text)

        sql_text = sql_bytes.decode('utf-8')
        # Aucune valeur de secret (enveloppée) dans le dump SQL.
        for label, secret in (
                ('phrase de passe', wrapped_passphrase),
                ('client_secret Google', wrapped_client_secret),
                ('jeton OAuth', wrapped_token),
        ):
            if not secret:
                continue
            check(f'Secret {label} absent du dump SQL', secret not in sql_text)
        # La ligne INSERT de cloud_backup_settings comporte exactement une
        # occurrence de chaque colonne secrète, toutes à NULL.
        m = re.search(r'INSERT INTO cloud_backup_settings \((.*?)\) VALUES \((.*?)\);',
                      sql_text, flags=re.DOTALL)
        check('INSERT cloud_backup_settings trouvé dans le dump', m is not None)
        if m:
            cols = [c.strip().strip('"') for c in m.group(1).split(',')]
            values = [v.strip() for v in m.group(2).split(',')]
            by_name = dict(zip(cols, values))
            redacted_ok = all(
                by_name.get(c) == 'NULL' for c in SECRET_COLUMNS['cloud_backup_settings'])
            check('Colonnes secrètes à NULL dans la ligne INSERT settings', redacted_ok)
        zf.close()

        # ── 3. Base vierge ──────────────────────────────────────────────────────
        print('Étape 3 — Création d’une base PostgreSQL vierge...')
        host = os.environ.get('DB_HOST', 'localhost')
        port = os.environ.get('DB_PORT', '5432')
        user = os.environ.get('DB_USER', 'postgres')
        password = os.environ.get('DB_PASSWORD', '')
        admin = psycopg2.connect(host=host, port=port, user=user, password=password,
                                 dbname='postgres')
        admin.autocommit = True
        cur = admin.cursor()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        virgin_name = f'ciento_validation_{ts}'
        cur.execute(f'DROP DATABASE IF EXISTS {virgin_name}')
        cur.execute(f'CREATE DATABASE {virgin_name}')
        cur.close()
        admin.close()
        print(f'  Base vierge créée : {virgin_name}')

    restore_upload = tempfile.mkdtemp(prefix='ciento_uploads_')
    prod = virgin = None
    vapp = None
    try:
        # ── 4. Restauration dans la base vierge ─────────────────────────────────
        print('Étape 4 — Restauration de l’archive dans la base vierge...')
        from urllib.parse import quote, quote_plus
        virgin_uri = (f'postgresql://{quote_plus(user)}:{quote_plus(password)}'
                      f'@{host}:{port}/{quote(virgin_name, safe="")}')

        class VirginConfig(ValidationConfig):
            SQLALCHEMY_DATABASE_URI = virgin_uri
            UPLOAD_FOLDER = restore_upload

        vapp = create_app(VirginConfig)
        backup_service.GoogleDriveService = LocalDriveService
        with vapp.app_context():
            # Schéma identique à une installation fraîche (init_db.py) : tables
            # créées mais vides, puis remplacées par la restauration.
            db.create_all()
            vrecord = CloudBackupRecord(backup_type='Manual', status='running',
                                        triggered_by='Validation automatique',
                                        drive_file_id=archive_file_id,
                                        file_name=vrec.file_name)
            db.session.add(vrecord)
            db.session.commit()
            vservice = backup_service.BackupService(vapp)
            label = vservice.restore_backup(vrecord.id, passphrase)
            check('Restauration exécutée sans erreur', label is not None, label)

        # ── 5. Comparaison production vs restauré ──────────────────────────────────
        print('Étape 5 — Comparaison des données...')
        prod = psycopg2.connect(host=host, port=port, user=user, password=password,
                                dbname=os.environ.get('DB_NAME', 'ciento_immobilier'))
        virgin = psycopg2.connect(host=host, port=port, user=user, password=password,
                                  dbname=virgin_name)

        # Supprimer la ligne « fantôme » (validation) des deux côtés avant
        # la comparaison pour que cloud_backups soit identique.
        for conn, where_id in ((prod, validation_rec_id), (virgin, validation_rec_id)):
            cur = conn.cursor()
            cur.execute('DELETE FROM cloud_backups WHERE id = %s', (where_id,))
            conn.commit()
            cur.close()

        prod_snap = snapshot(prod)
        virgin_snap = snapshot(virgin)
        all_ok = True
        for table in db.metadata.sorted_tables:
            name = table.name
            p, v = prod_snap.get(name, []), virgin_snap.get(name, [])
            if len(p) != len(v):
                check(f'{name} : {len(p)} vs {len(v)} lignes', False, 'nombre de lignes différent')
                all_ok = False
                continue
            if name == 'cloud_backup_settings':
                # Colonnes secrètes volontairement NULL après restauration ;
                # la phrase de passe est ré-injectée avec la clé locale (nouvelle
                # enveloppe + horodatage), donc les colonnes passphrase_set_at et
                # updated_at diffèrent légitimement de la production.
                p_row = p[0] if p else ()
                v_row = v[0] if v else ()
                cols = [c.name for c in table.columns]
                mutable = SECRET_COLUMNS.get(name, ()) | {'passphrase_set_at', 'updated_at'}
                stable_ok = all(
                    p_row[i] == v_row[i]
                    for i, c in enumerate(cols)
                    if c not in mutable)
                check(f'{name} : colonnes stables identiques', stable_ok)
                google_secrets = SECRET_COLUMNS.get(name, ()) - {'encryption_passphrase_wrapped'}
                secrets_ok = all(
                    v_row[i] == 'NULL'
                    for i, c in enumerate(cols)
                    if c in google_secrets)
                check(f'{name} : identifiants Google NULL dans la base restaurée', secrets_ok)
                pass_idx = cols.index('encryption_passphrase_wrapped')
                restored_pass = v_row[pass_idx]
                try:
                    with app.app_context():
                        unwrapped = crypto_service.unwrap_secret(restored_pass)
                    check(f'{name} : phrase de passe ré-injectée et déchiffrable',
                          unwrapped == passphrase)
                except Exception:
                    check(f'{name} : phrase de passe ré-injectée et déchiffrable', False)
                continue
            if p != v:
                check(f'{name} : contenu complet identique', False)
                all_ok = False
                continue
            check(f'{name} : {len(p)} lignes, contenu identique', True)

        # Intégrité des clés étrangères côté restauré.
        checked, orphans = orphan_check(virgin, None)
        check(f'Intégrité des clés étrangères ({checked} contraintes)',
              not orphans, f'{len(orphans)} orphelins' if orphans else 'aucun orphelin')
        if orphans:
            all_ok = False
            for conname, child, nb in orphans:
                print(f'    - {child} ({conname}) : {nb} lignes orphelines')

        # Uploads octet pour octet.
        print('  Comparaison des uploads (fichiers stockés)...')
        def walk(root):
            out = {}
            for r, _, files in os.walk(root):
                for f in files:
                    full = os.path.join(r, f)
                    rel = os.path.relpath(full, root)
                    with open(full, 'rb') as fh:
                        out[rel] = hashlib.sha256(fh.read()).hexdigest()
            return out

        prod_uploads = walk(app.config['UPLOAD_FOLDER'])
        rest_uploads = walk(restore_upload)
        check('Même nombre de fichiers uploadés',
              len(prod_uploads) == len(rest_uploads),
              f'{len(prod_uploads)} vs {len(rest_uploads)}')
        common = set(prod_uploads) & set(rest_uploads)
        missing = set(prod_uploads) - set(rest_uploads)
        extra = set(rest_uploads) - set(prod_uploads)
        check('Tous les fichiers uploadés restaurés', not missing,
              f'manquants : {sorted(missing)[:5]}' if missing else '')
        check('Aucun fichier inattendu restauré', not extra,
              f'inattendus : {sorted(extra)[:5]}' if extra else '')
        byte_ok = all(prod_uploads[r] == rest_uploads[r] for r in common)
        check('Fichiers identiques octet pour octet', byte_ok)

        prod.close()
        virgin.close()
        prod = virgin = None
    finally:
        # ── 6. Nettoyage ─────────────────────────────────────────────────────
        print('Étape 6 — Nettoyage...')
        for conn in (prod, virgin):
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        if vapp is not None:
            # Libère les connexions du moteur de la base vierge pour permettre
            # son DROP (sinon « being accessed by other users »).
            with vapp.app_context():
                db.engine.dispose()
        try:
            admin = psycopg2.connect(host=host, port=port, user=user,
                                     password=password, dbname='postgres')
            admin.autocommit = True
            cur = admin.cursor()
            cur.execute(f'DROP DATABASE IF EXISTS {virgin_name}')
            cur.close()
            admin.close()
        except Exception as exc:
            print(f'  (base vierge {virgin_name} non supprimée : {exc})')
        shutil.rmtree(restore_upload, ignore_errors=True)
        with app.app_context():
            rec = db.session.get(CloudBackupRecord, validation_rec_id)
            if rec:
                db.session.delete(rec)
                db.session.commit()
        print(f'  Base vierge {virgin_name} supprimée, ligne de validation purgée.')

    # ── Bilan ────────────────────────────────────────────────────────────────
    fails = [r for r in RESULTS if not r[1]]
    print('\n' + '=' * 60)
    print(f'BILAN : {len(RESULTS) - len(fails)}/{len(RESULTS)} contrôles OK')
    if fails:
        print('ÉCHECS :')
        for label, ok, detail in fails:
            print(f'  - {label} : {detail}')
        return 1
    print('Validation bout-en-bout SAUVE-TOUT : cycle sauvegarde -> restauration '
          'OK sur base PostgreSQL vierge.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
