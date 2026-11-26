from django.test import TestCase
from rest_framework.test import APIClient
from apps.common.crypto import encrypt_pan, decrypt_pan, mask_pan
from apps.clients.validators import validate_pan_format, validate_gstin_format

class CommonCryptoTests(TestCase):
    def test_pan_encryption_decryption(self):
        original = 'ABCDE1234F'
        encrypted = encrypt_pan(original)
        self.assertNotEqual(original, encrypted)
        decrypted = decrypt_pan(encrypted)
        self.assertEqual(original, decrypted)

    def test_pan_masking(self):
        pan = 'ABCDE1234F'
        masked = mask_pan(pan)
        self.assertEqual(masked, 'XXXXX1234X')

    def test_pan_validation(self):
        self.assertEqual(validate_pan_format('abcde1234f'), 'ABCDE1234F')
        with self.assertRaises(Exception):
            validate_pan_format('INVALID123')

    def test_gstin_validation(self):
        valid_gstin = '27ABCDE1234F1Z0'
        self.assertEqual(validate_gstin_format(valid_gstin, pan='ABCDE1234F'), valid_gstin)

        # Mismatched PAN inside GSTIN
        with self.assertRaises(Exception):
            validate_gstin_format('27XYZPQ9999M1Z5', pan='ABCDE1234F')

    def test_healthz_endpoint(self):
        client = APIClient()
        response = client.get('/healthz')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'healthy')
        self.assertEqual(response.data['checks']['database'], 'ok')

    def test_root_endpoint_json(self):
        client = APIClient()
        response = client.get('/', HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'healthy')
        self.assertIn('docs', response.data['endpoints'])

    def test_root_endpoint_browser_redirect(self):
        client = APIClient()
        response = client.get('/', HTTP_ACCEPT='text/html,application/xhtml+xml')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/api/docs/')

    def test_openapi_schema_endpoint(self):
        client = APIClient()
        response = client.get('/api/schema/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('openapi', response.data)
