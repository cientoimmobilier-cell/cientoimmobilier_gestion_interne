import secrets
from urllib.parse import urlparse

from flask import g


def sanitize_external_url(value):
    """Ne conserve que des URLs http(s) absolues ; renvoie '' sinon."""
    if not value:
        return ''
    value = str(value).strip()
    try:
        parsed = urlparse(value)
    except ValueError:
        return ''
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.netloc:
        return ''
    return value


def generate_nonce():
    if 'csp_nonce' not in g:
        g.csp_nonce = secrets.token_urlsafe(16)
    return g.csp_nonce


def build_csp():
    nonce = generate_nonce()
    csp = {
        'default-src': ["'self'"],
        'script-src': [
            "'self'",
            f"'nonce-{nonce}'",
        ],
        'style-src': [
            "'self'",
            "'unsafe-inline'",
        ],
        'font-src': ["'self'"],
        'img-src': [
            "'self'",
            "data:",
            "blob:",
        ],
        'connect-src': ["'self'"],
        'frame-ancestors': ["'self'"],
        'form-action': ["'self'"],
        'base-uri': ["'self'"],
        'object-src': ["'none'"],
    }
    return '; '.join(
        f"{key} {' '.join(value)}" for key, value in csp.items()
    )


SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'SAMEORIGIN',
    'X-XSS-Protection': '1; mode=block',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': (
        'geolocation=(), camera=(), microphone=(), '
        'midi=(), sync-xhr=(), accelerometer=(), '
        'gyroscope=(), magnetometer=(), '
        'payment=(), usb=(), display-capture=()'
    ),
}
