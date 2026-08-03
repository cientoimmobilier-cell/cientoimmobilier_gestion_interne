"""
Manifest des archives de sauvegarde CIENTO IMMOBILIER.

Chaque archive chiffrée contient un ``sauvegarde/manifest.json`` qui décrit :
- le format de sauvegarde (``format_version``) et sa signature ;
- la version du logiciel qui l'a produite ;
- l'empreinte SHA-256 du schéma PostgreSQL (``schema_fingerprint``) et la liste
  des tables — la restauration refuse toute archive dont le schéma ne correspond
  pas au code actuellement installé ;
- la date de création et le type de sauvegarde ;
- les checksums SHA-256 des fichiers (``base_de_donnees.sql``) ;
- le chiffrement utilisé.

Le manifest est embarqué DANS l'archive, elle-même chiffrée (AES-256-GCM) :
son intégrité et son authenticité sont donc garanties par le tag GCM.
"""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.schema import CreateTable

from app import db
from app.version import CIENTO_VERSION
from app.services.crypto_service import PBKDF2_ITERATIONS

# Version du FORMAT d'archive (indépendante de la version du logiciel).
# Incrémenter lors de toute évolution incompatible de la structure interne
# (membres du ZIP, manifest, dump) pour que les anciennes archives soient
# refusées proprement par les nouvelles versions du logiciel.
BACKUP_FORMAT_VERSION = 2

FORMAT_SIGNATURE = 'ciento-backup'
MANIFEST_MEMBER = 'manifest.json'
SQL_MEMBER = 'base_de_donnees.sql'
ENCRYPTION_ALGORITHM = 'AES-256-GCM'
ENCRYPTION_KDF = 'PBKDF2-HMAC-SHA256'


class ManifestValidationError(Exception):
    """Le manifest d'une archive est absent, corrompu ou incompatible."""


def compute_sha256(data):
    """Empreinte SHA-256 hexadécimale d'un contenu binaire."""
    return hashlib.sha256(data).hexdigest()


def compute_schema_fingerprint():
    """Empreinte SHA-256 du schéma attendu par le code actuel.

    Le schéma est dérivé des métadonnées SQLAlchemy (CreateTable compilé pour le
    dialecte courant) : deux machines qui exécutent la même version du code
    produisent la même empreinte ; un code mis à jour produit une empreinte
    différente et la restauration est alors refusée.
    """
    ddl = [str(CreateTable(t).compile(dialect=db.engine.dialect))
           for t in db.metadata.sorted_tables]
    return compute_sha256('\n'.join(ddl).encode('utf-8'))


def build_manifest(backup_type, included_groups, sql_bytes, upload_count):
    """Construit le dictionnaire manifest d'une nouvelle sauvegarde."""
    return {
        'format': FORMAT_SIGNATURE,
        'format_version': BACKUP_FORMAT_VERSION,
        'software_version': CIENTO_VERSION,
        'created_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'backup_type': backup_type,
        'included_groups': sorted(included_groups),
        'database': {
            'dialect': db.engine.dialect.name,
            'schema_fingerprint': compute_schema_fingerprint(),
            'tables': [t.name for t in db.metadata.sorted_tables],
        },
        'files': {
            'upload_count': upload_count,
            'checksums': {
                SQL_MEMBER: 'sha256:' + compute_sha256(sql_bytes),
            },
        },
        'encryption': {
            'algorithm': ENCRYPTION_ALGORITHM,
            'kdf': ENCRYPTION_KDF,
            'pbkdf2_iterations': PBKDF2_ITERATIONS,
        },
    }


def manifest_bytes(backup_type, included_groups, sql_bytes, upload_count):
    """Sérialise le manifest en JSON UTF-8 pour écriture dans l'archive."""
    payload = build_manifest(backup_type, included_groups, sql_bytes, upload_count)
    return json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')


def load_manifest(raw):
    """Parse un manifest binaire JSON. Lève ManifestValidationError si invalide."""
    try:
        manifest = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestValidationError(
            'Manifest illisible ou corrompu dans l\'archive.') from exc
    if not isinstance(manifest, dict):
        raise ManifestValidationError('Manifest invalide dans l\'archive.')
    return manifest


def validate_manifest(manifest, sql_bytes):
    """Vérifie la compatibilité d'une archive avec le logiciel installé.

    Contrôles : signature du format, version du format, empreinte du schéma,
    liste des tables, checksum du dump SQL. Lève ManifestValidationError avec un
    message explicite en cas d'incompatibilité (le restore ne doit JAMAIS
    appliquer un schéma inconnu).
    """
    if manifest.get('format') != FORMAT_SIGNATURE:
        raise ManifestValidationError(
            'Archive invalide : signature de format inconnue '
            f'("{manifest.get("format")}"). Vérifiez la provenance de la sauvegarde.')

    fmt = manifest.get('format_version')
    if fmt != BACKUP_FORMAT_VERSION:
        raise ManifestValidationError(
            f'Format de sauvegarde incompatible (archive version {fmt}, '
            f'logiciel version {BACKUP_FORMAT_VERSION}). '
            'Installez une version du logiciel compatible ou utilisez une '
            'sauvegarde plus récente.')

    db_info = manifest.get('database') or {}
    archived_fingerprint = db_info.get('schema_fingerprint')
    current_fingerprint = compute_schema_fingerprint()
    if not archived_fingerprint or archived_fingerprint != current_fingerprint:
        raise ManifestValidationError(
            'Schéma de base de données incompatible : la sauvegarde a été créée '
            'par une version du logiciel dont le schéma diffère du logiciel '
            'installé. La restauration est refusée pour éviter toute perte ou '
            'corruption de données.')

    archived_tables = sorted(db_info.get('tables') or [])
    current_tables = sorted(t.name for t in db.metadata.sorted_tables)
    if archived_tables != current_tables:
        missing = sorted(set(current_tables) - set(archived_tables))
        extra = sorted(set(archived_tables) - set(current_tables))
        detail = []
        if missing:
            detail.append(f'tables manquantes: {", ".join(missing)}')
        if extra:
            detail.append(f'tables inconnues: {", ".join(extra)}')
        raise ManifestValidationError(
            'Schéma de base de données incompatible : la liste des tables diffère '
            f'({"; ".join(detail)}). Restauration refusée.')

    expected = (manifest.get('files', {}).get('checksums', {}) or {}).get(SQL_MEMBER)
    actual = 'sha256:' + compute_sha256(sql_bytes)
    if not expected or expected != actual:
        raise ManifestValidationError(
            'Checksum du dump SQL invalide : le fichier base_de_donnees.sql ne '
            'correspond pas au manifest. Archive corrompue ou modifiée, '
            'restauration refusée.')
