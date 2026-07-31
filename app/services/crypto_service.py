"""
Service de chiffrement du module Sauvegarde Cloud.

- Chiffrement des archives : AES-256-GCM, cle derivee d'une phrase de passe
  (PBKDF2-HMAC-SHA256). Format portable : magic | salt | nonce | ciphertext.
- Enveloppe des secrets applicatifs (jeton Google, client_id/secret, phrase
  de passe) : Fernet, cle derivee du SECRET_KEY de Flask. Un compromis de la
  seule base ne suffit donc pas a lire les secrets.
"""
import base64
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b'CIENTOBK1'
SALT_SIZE = 16
NONCE_SIZE = 12
PBKDF2_ITERATIONS = 200_000
MIN_PASSPHRASE_LENGTH = 12


class CryptoError(Exception):
    pass


def derive_key(passphrase, salt):
    """Derive une cle AES-256 de 32 octets a partir de la phrase de passe."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(passphrase.encode('utf-8'))


def encrypt_bytes(data, passphrase):
    """Chiffre data (bytes) avec AES-256-GCM. Retourne magic|salt|nonce|ct."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    if not passphrase:
        raise CryptoError('La phrase de passe est vide.')
    salt = os.urandom(SALT_SIZE)
    nonce = os.urandom(NONCE_SIZE)
    key = derive_key(passphrase, salt)
    ciphertext = AESGCM(key).encrypt(nonce, data, None)
    return MAGIC + salt + nonce + ciphertext


def decrypt_bytes(payload, passphrase):
    """Inverse de encrypt_bytes. Leve CryptoError si magic/phrase invalides."""
    if not payload.startswith(MAGIC):
        raise CryptoError('Format de fichier inconnu ou corrompu.')
    salt = payload[len(MAGIC):len(MAGIC) + SALT_SIZE]
    nonce = payload[len(MAGIC) + SALT_SIZE:len(MAGIC) + SALT_SIZE + NONCE_SIZE]
    ciphertext = payload[len(MAGIC) + SALT_SIZE + NONCE_SIZE:]
    key = derive_key(passphrase, salt)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception:
        raise CryptoError('Phrase de passe invalide ou fichier corrompu.')


def _secret_passphrase(secret_key=None):
    """Passphrase interne derivee du SECRET_KEY de l'application."""
    from flask import current_app
    key = secret_key or current_app.config.get('SECRET_KEY')
    if not key:
        raise CryptoError('SECRET_KEY manquant pour envelopper le secret.')
    return str(key)


def wrap_secret(plaintext, secret_key=None):
    """Chiffre un secret applicatif en AES-256-GCM (cle du SECRET_KEY)."""
    if plaintext is None:
        return None
    encrypted = encrypt_bytes(str(plaintext), _secret_passphrase(secret_key))
    return base64.b64encode(encrypted).decode('ascii')


def unwrap_secret(token, secret_key=None):
    """Inverse de wrap_secret. Retourne None si token absent."""
    if not token:
        return None
    try:
        payload = base64.b64decode(token.encode('ascii'))
    except Exception:
        raise CryptoError('Secret stocke corrompu.')
    try:
        return decrypt_bytes(payload, _secret_passphrase(secret_key)).decode('utf-8')
    except CryptoError:
        raise CryptoError('Secret invalide (SECRET_KEY different ?).')


def generate_passphrase():
    """Genere une phrase de passe forte (min. 32 caracteres)."""
    alphabet = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789'
    words = ['-'.join(''.join(secrets.choice(alphabet) for _ in range(6)) for _ in range(3))]
    return words[0]
