import secrets

from flask import g


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
            "https://cdn.jsdelivr.net",
            f"'nonce-{nonce}'",
        ],
        'style-src': [
            "'self'",
            "https://cdn.jsdelivr.net",
            "https://cdnjs.cloudflare.com",
            "https://fonts.googleapis.com",
            "'unsafe-inline'",
        ],
        'font-src': [
            "'self'",
            "https://cdnjs.cloudflare.com",
            "https://cdn.jsdelivr.net",
            "https://fonts.googleapis.com",
            "https://fonts.gstatic.com",
            "data:",
        ],
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
