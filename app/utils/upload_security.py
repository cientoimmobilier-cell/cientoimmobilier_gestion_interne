import logging
import os
from datetime import datetime

from flask import current_app
from werkzeug.utils import secure_filename

from app.utils.helpers import safe_path_join

logger = logging.getLogger(__name__)

# --- Extensions DANGEREUSES systématiquement bloquées ---
BLOCKED_EXTENSIONS = {
    'exe', 'bat', 'cmd', 'com', 'msi', 'scr', 'vbs', 'vbe', 'js', 'jse',
    'wsf', 'wsh', 'ps1', 'psm1', 'psd1', 'ps1xml', 'pssc', 'psc1',
    'jar', 'class', 'swf', 'wasm',
    'sh', 'bash', 'csh', 'zsh', 'ksh',
    'php', 'php3', 'php4', 'php5', 'phtml', 'pht', 'shtml',
    'asp', 'aspx', 'asa', 'ascx', 'asmx',
    'cfm', 'cfc', 'pl', 'py', 'pyc', 'pyo', 'rb', 'cgi',
    'dll', 'sys', 'ocx', 'drv',
    'hta', 'html', 'htm', 'xhtml', 'shtm', 'sht',
    'jsp', 'jspx', 'war', 'sln',
}

# --- Extensions autorisées par catégorie ---
ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
ALLOWED_DOCUMENTS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}
ALLOWED_PDFS = {'pdf'}
ALLOWED_EXCEL = {'xls', 'xlsx'}

# --- Magic bytes : (pattern, format_mask) -> (extensions, description) ---
# Le format_mask est un masque de bytes : None = vérification exacte,
# un bytes avec des None indique des positions ignorées
class MagicRule:
    __slots__ = ('pattern', 'mask', 'extensions', 'mime')

    def __init__(self, pattern, extensions, mime):
        self.pattern = pattern
        self.extensions = extensions
        self.mime = mime

    def matches(self, header):
        if len(header) < len(self.pattern):
            return False
        for i, b in enumerate(self.pattern):
            if header[i] != b:
                return False
        return True

MAGIC_RULES = {
    'jpg': MagicRule(b'\xff\xd8\xff', ('jpg', 'jpeg'), 'image/jpeg'),
    'png': MagicRule(b'\x89PNG\r\n\x1a\n', ('png',), 'image/png'),
    'gif87': MagicRule(b'GIF87a', ('gif',), 'image/gif'),
    'gif89': MagicRule(b'GIF89a', ('gif',), 'image/gif'),
    'webp': MagicRule(b'RIFF', ('webp',), 'image/webp'),
    'pdf': MagicRule(b'%PDF', ('pdf',), 'application/pdf'),
    'zip_office': MagicRule(b'PK\x03\x04', ('docx', 'xlsx', 'zip'), 'application/zip'),
    'ole2': MagicRule(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1', ('doc', 'xls'), 'application/x-ole-storage'),
}

def check_blocked_extension(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext in BLOCKED_EXTENSIONS

def check_allowed_extension(filename, allowed_set):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext in allowed_set

def get_magic_rule(file_stream):
    header = file_stream.read(16)
    file_stream.seek(0)
    if len(header) < 4:
        return None
    for rule in MAGIC_RULES.values():
        if rule.matches(header):
            return rule
    return None

def validate_webp_content(file_stream):
    header = file_stream.read(12)
    file_stream.seek(0)
    if len(header) < 12:
        return False
    if header[:4] != b'RIFF':
        return False
    if header[8:12] != b'WEBP':
        return False
    return True

def validate_image_content_secure(file_stream):
    rule = get_magic_rule(file_stream)
    if rule is None:
        return False, None
    if rule.extensions[0] == 'webp':
        if not validate_webp_content(file_stream):
            return False, None
    return True, rule.extensions[0]

def validate_document_content(file_stream):
    rule = get_magic_rule(file_stream)
    if rule is None:
        return False, None
    return True, rule.extensions[0]

def validate_excel_content(file_stream):
    header = file_stream.read(8)
    file_stream.seek(0)
    if header.startswith(b'PK\x03\x04'):
        return True
    if header.startswith(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'):
        return True
    return False

def check_file_size_before_read(file_storage, max_size):
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    return size <= max_size

def secure_save_path(upload_dir, original_filename, prefix=''):
    safe_name = secure_filename(original_filename)
    if not safe_name:
        safe_name = 'file'
    ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
    unique_name = f"{prefix}{ts}_{safe_name}" if prefix else f"{ts}_{safe_name}"
    abs_path = safe_path_join(upload_dir, unique_name)
    if abs_path is None:
        raise ValueError("Path traversal détecté — opération refusée.")
    os.makedirs(upload_dir, exist_ok=True)
    return abs_path, unique_name

# --- ClamAV integration (optionnel) ---
# Mode de connexion détecté : 'unix', 'network' ou None (indisponible).
_clamav_mode = None

def is_clamav_available():
    global _clamav_mode
    if _clamav_mode is not None:
        return _clamav_mode != 'unavailable'
    try:
        import pyclamd
    except ImportError:
        _clamav_mode = 'unavailable'
        logger.warning("[UPLOAD] pyclamd non installé — upload sans scan antivirus")
        return False

    # Sur Windows, le socket Unix n'existe pas : le démon ClamAV écoute
    # généralement en TCP sur 127.0.0.1:3310.
    if os.name == 'nt':
        factories = [pyclamd.ClamdNetworkSocket, pyclamd.ClamdUnixSocket]
    else:
        factories = [pyclamd.ClamdUnixSocket, pyclamd.ClamdNetworkSocket]

    for factory in factories:
        try:
            cd = factory()
            cd.ping()
            _clamav_mode = 'network' if factory is pyclamd.ClamdNetworkSocket else 'unix'
            logger.info("[UPLOAD] ClamAV détecté (socket %s)", _clamav_mode)
            return True
        except Exception:
            continue
    _clamav_mode = 'unavailable'
    logger.warning("[UPLOAD] ClamAV non disponible — upload sans scan antivirus")
    return False

def _clamd_connection():
    import pyclamd
    if _clamav_mode == 'network':
        return pyclamd.ClamdNetworkSocket()
    return pyclamd.ClamdUnixSocket()

def scan_with_clamav(filepath):
    if not is_clamav_available():
        return True, None
    try:
        cd = _clamd_connection()
        result = cd.scan_file(filepath)
        if result:
            for path, status in result.items():
                if status != 'OK':
                    logger.error(f"[UPLOAD] ClamAV a détecté une menace dans {filepath}: {status}")
                    return False, str(status)
        return True, None
    except Exception as e:
        logger.error(f"[UPLOAD] Erreur scan ClamAV {filepath}: {e}")
        return True, None

def log_upload(user_id, filename, file_size, category, status, details=''):
    logger.info(
        f"[UPLOAD] user={user_id} | fichier={filename} | taille={file_size} | "
        f"catégorie={category} | statut={status} | {details}"
    )

class UploadValidationError(Exception):
    def __init__(self, message, code='UPLOAD_ERROR'):
        self.code = code
        self.message = message
        super().__init__(self.message)

def validate_and_save_upload(
    file_storage,
    upload_subdir,
    allowed_extensions,
    max_size,
    category='fichier',
    validate_magic=True,
    prefix='',
    user_id=None
):
    if not file_storage or not file_storage.filename:
        raise UploadValidationError("Aucun fichier fourni.", 'NO_FILE')

    original_name = file_storage.filename

    if check_blocked_extension(original_name):
        log_upload(user_id, original_name, 0, category, 'BLOQUÉ', 'Extension interdite')
        raise UploadValidationError(
            f"Le fichier {original_name} a une extension interdite pour des raisons de sécurité.",
            'EXTENSION_BLOCKED'
        )

    if not check_allowed_extension(original_name, allowed_extensions):
        log_upload(user_id, original_name, 0, category, 'BLOQUÉ', 'Extension non autorisée')
        raise UploadValidationError(
            f"Extension du fichier non autorisée. Types acceptés : {', '.join(sorted(allowed_extensions))}.",
            'EXTENSION_NOT_ALLOWED'
        )

    if not check_file_size_before_read(file_storage, max_size):
        log_upload(user_id, original_name, 0, category, 'BLOQUÉ', f'Taille > {max_size} octets')
        raise UploadValidationError(
            f"Le fichier dépasse la taille maximale autorisée "
            f"({max_size // (1024*1024)} Mo).",
            'FILE_TOO_LARGE'
        )

    if validate_magic:
        detected = get_magic_rule(file_storage)
        if detected is None:
            log_upload(user_id, original_name, 0, category, 'BLOQUÉ', 'Magic bytes invalides')
            raise UploadValidationError(
                "Le contenu du fichier ne correspond pas à un format valide.",
                'INVALID_CONTENT'
            )
        ext_uploaded = original_name.rsplit('.', 1)[1].lower() if '.' in original_name else ''
        ext_detected_set = set(detected.extensions)
        if ext_uploaded not in ext_detected_set and ext_uploaded not in detected.extensions:
            log_upload(user_id, original_name, 0, category, 'BLOQUÉ',
                       f'Extension {ext_uploaded} != contenu {detected.extensions[0]}')
            raise UploadValidationError(
                "Le type réel du fichier ne correspond pas à son extension.",
                'MIME_MISMATCH'
            )

    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], upload_subdir)
    safe_path, unique_name = secure_save_path(upload_dir, original_name, prefix)

    file_storage.seek(0)
    file_storage.save(safe_path)

    file_size = os.path.getsize(safe_path)

    threat_found, threat_name = scan_with_clamav(safe_path)
    if not threat_found:
        os.remove(safe_path)
        log_upload(user_id, original_name, file_size, category, 'BLOQUÉ',
                   f'ClamAV: {threat_name}')
        raise UploadValidationError(
            f"Le fichier a été rejeté par l'antivirus: {threat_name}",
            'VIRUS_DETECTED'
        )

    # Le chemin stocké en base porte le préfixe "uploads/" pour que l'URL
    # /static/uploads/... (static_folder = app/static) corresponde à l'emplacement
    # réel (UPLOAD_FOLDER + upload_subdir). upload_subdir est relatif à
    # UPLOAD_FOLDER (ex. 'photos', 'documents').
    rel_path = f"uploads/{upload_subdir}/{unique_name}".replace('\\', '/')

    log_upload(user_id, original_name, file_size, category, 'ACCEPTÉ', f'saved_as={unique_name}')

    return safe_path, rel_path, unique_name, file_size
