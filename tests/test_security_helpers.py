import unittest


class TestNeutralizeFormula(unittest.TestCase):
    def test_formula_prefixes_neutralized(self):
        from app.utils.helpers import neutralize_formula
        self.assertEqual(neutralize_formula('=SUM(A1:B1)'), "'=SUM(A1:B1)")
        self.assertEqual(neutralize_formula('+cmd'), "'+cmd")
        self.assertEqual(neutralize_formula('@SUM'), "'@SUM")
        self.assertEqual(neutralize_formula('=HYPERLINK("http://x")'), "'=HYPERLINK(\"http://x\")")

    def test_negative_numbers_preserved(self):
        from app.utils.helpers import neutralize_formula
        self.assertEqual(neutralize_formula('-1500.50'), '-1500.50')
        self.assertEqual(neutralize_formula('-42'), '-42')

    def test_normal_text_preserved(self):
        from app.utils.helpers import neutralize_formula
        self.assertEqual(neutralize_formula('Jean DUPONT'), 'Jean DUPONT')
        self.assertEqual(neutralize_formula('Rue de la Paix'), 'Rue de la Paix')
        self.assertEqual(neutralize_formula(''), '')
        self.assertEqual(neutralize_formula(None), None)

    def test_negative_non_numeric_neutralized(self):
        from app.utils.helpers import neutralize_formula
        self.assertEqual(neutralize_formula('-test command'), "'-test command")


class TestSanitizeExternalUrl(unittest.TestCase):
    def test_allows_http_https(self):
        from app.utils.security import sanitize_external_url
        self.assertEqual(
            sanitize_external_url('https://www.airbnb.com/rooms/123'),
            'https://www.airbnb.com/rooms/123')
        self.assertEqual(
            sanitize_external_url('http://example.com'),
            'http://example.com')

    def test_rejects_javascript_and_others(self):
        from app.utils.security import sanitize_external_url
        self.assertEqual(sanitize_external_url('javascript:alert(1)'), '')
        self.assertEqual(sanitize_external_url('data:text/html,<script>'), '')
        self.assertEqual(sanitize_external_url('vbscript:msgbox(1)'), '')
        self.assertEqual(sanitize_external_url('file:///etc/passwd'), '')
        self.assertEqual(sanitize_external_url('relative/path'), '')
        self.assertEqual(sanitize_external_url(''), '')
        self.assertEqual(sanitize_external_url(None), '')


class TestPdfEscape(unittest.TestCase):
    def test_pdf_esc(self):
        from app.services.pdf_service import esc
        self.assertEqual(esc('<b>&alert</b>'), '&lt;b&gt;&amp;alert&lt;/b&gt;')
        self.assertEqual(esc(None), '')
        self.assertEqual(esc('Jean'), 'Jean')


class TestGenerateRandomPassword(unittest.TestCase):
    def test_random_admin_password(self):
        from app.utils.helpers import generate_random_password
        p1 = generate_random_password(16)
        p2 = generate_random_password(16)
        self.assertEqual(len(p1), 16)
        self.assertNotEqual(p1, p2)
        self.assertTrue(p1.isprintable())


if __name__ == '__main__':
    unittest.main()
