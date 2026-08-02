import unittest
from app import create_app
from config import Config


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = 'cle-de-test-ciento-immobilier-2026-32caracteres'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


class TestWebSecurity(unittest.TestCase):
    """Vérifie les garanties web de la remédiation : routes POST-only,
    CSP sans hôtes externes, cache statique, assets vendor localisés.
    """

    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()

    def tearDown(self):
        self.ctx.pop()

    # ── Routes d'export/PDF : GET interdit (commit-dans-GET corrigé) ──────────
    def _get_endpoint(self, endpoint, **kwargs):
        from flask import url_for
        with self.app.test_request_context():
            return url_for(endpoint, **kwargs)

    def test_export_routes_reject_get(self):
        cases = [
            ('transactions.export_transactions', {}),
            ('transactions.download_transaction_pdf', {'tx_id': 1}),
            ('transactions.download_payment_receipt_pdf_route', {'pay_id': 1}),
            ('properties.export_properties', {}),
            ('owners.export_owners', {}),
            ('clients.export_clients', {}),
            ('occupation.export_excel', {}),
            ('occupation.export_pdf', {'occ_id': 1}),
            ('airbnb.download_airbnb_pdf', {'bien_id': 1}),
        ]
        for endpoint, kwargs in cases:
            url = self._get_endpoint(endpoint, **kwargs)
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)

    def test_export_routes_accept_post(self):
        """POST atteint la protection login (302 vers /login) plutôt que 405."""
        url = self._get_endpoint('transactions.export_transactions')
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers.get('Location', ''))

    # ── CSP strict : aucun hôte externe, nonce présent ───────────────────────
    def test_csp_no_external_hosts(self):
        resp = self.client.get('/login')
        csp = resp.headers.get('Content-Security-Policy', '')
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertIn('nonce-', csp)
        for banned in ('cdn.jsdelivr', 'cdnjs.cloudflare', 'fonts.googleapis.com',
                       'fonts.gstatic.com', 'unsafe-eval'):
            self.assertNotIn(banned, csp)

    def test_security_headers_present(self):
        resp = self.client.get('/login')
        self.assertEqual(resp.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(resp.headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertEqual(resp.headers.get('Referrer-Policy'),
                         'strict-origin-when-cross-origin')
        self.assertIn('frame-ancestors', resp.headers.get('Content-Security-Policy', ''))

    # ── Cache statique ────────────────────────────────────────────────────────
    def test_vendor_assets_cache_long(self):
        resp = self.client.get('/static/vendor/bootstrap/css/bootstrap.min.css')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.headers.get('Cache-Control'),
            'public, max-age=31536000, immutable',
        )

    def test_static_assets_cache_day(self):
        resp = self.client.get('/static/css/custom.css')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get('Cache-Control'), 'public, max-age=86400')

    def test_dynamic_pages_no_cache(self):
        resp = self.client.get('/login')
        self.assertEqual(
            resp.headers.get('Cache-Control'),
            'no-cache, no-store, must-revalidate',
        )

    # ── Assets vendor localisés et servis sans réseau ────────────────────────
    def test_vendor_assets_available(self):
        assets = [
            '/static/vendor/bootstrap/css/bootstrap.min.css',
            '/static/vendor/bootstrap/js/bootstrap.bundle.min.js',
            '/static/vendor/fontawesome/css/all.min.css',
            '/static/vendor/fontawesome/webfonts/fa-solid-900.woff2',
            '/static/vendor/fontawesome/webfonts/fa-brands-400.woff2',
            '/static/vendor/chartjs/chart.umd.js',
            '/static/vendor/outfit/outfit.css',
            '/static/vendor/outfit/outfit-latin-400-normal.woff2',
        ]
        for path in assets:
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 200)
                resp.close()

    def test_login_page_renders(self):
        resp = self.client.get('/login')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Ciento', resp.data)


if __name__ == '__main__':
    unittest.main()
