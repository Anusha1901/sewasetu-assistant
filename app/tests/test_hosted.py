"""Hosted adapters: private references, failure handling and encrypted DB connections."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import documents as d
import runtime_db
import services


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'DOCUMENT_STORAGE': 'supabase',
            'SUPABASE_URL': 'https://exampleproject.supabase.co',
            'SUPABASE_SERVICE_ROLE_KEY': 'test-backend-only-secret',
            'SUPABASE_STORAGE_BUCKET': 'age-proofs'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def response(self, content=b'%PDF-test'):
        reply = Mock(status_code=200)
        reply.iter_content.return_value = [content]
        return reply

    def test_upload_is_private_random_reference_without_mobile(self):
        with patch.object(d.requests, 'request', return_value=self.response()) as request:
            ref = d.save(b'%PDF-test', '.pdf')
        self.assertRegex(ref, r'^supabase://age-proofs/proofs/[a-f0-9]{48}\.pdf$')
        self.assertNotIn('secret', ref)
        self.assertEqual(request.call_args.kwargs['headers']['x-upsert'], 'false')
        self.assertFalse(request.call_args.kwargs['allow_redirects'])

    def test_download_requires_backend_auth(self):
        with patch.object(d.requests, 'request', return_value=self.response()) as request:
            self.assertEqual(d.read('supabase://age-proofs/proofs/' + 'a' * 48 + '.pdf'), b'%PDF-test')
        self.assertIn('/object/authenticated/age-proofs/', request.call_args.args[1])
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'], 'Bearer test-backend-only-secret')

    def test_arbitrary_urls_buckets_and_traversal_rejected_without_request(self):
        with patch.object(d.requests, 'request') as request:
            for ref in ('supabase://public/proofs/' + 'a' * 48 + '.pdf',
                        'supabase://age-proofs/../../secret.pdf',
                        'supabase://age-proofs/proofs/token.exe'):
                with self.assertRaises(d.StorageUnavailable):
                    d.read(ref)
            request.assert_not_called()

    def test_error_does_not_include_provider_body_or_secret(self):
        reply = Mock(status_code=403, text='private provider response')
        with patch.object(d.requests, 'request', return_value=reply):
            with self.assertRaises(d.StorageUnavailable) as error:
                d.save(b'proof', '.pdf')
        self.assertNotIn('private provider', str(error.exception))
        self.assertNotIn('secret', str(error.exception))

    def test_storage_outage_blocks_submission_instead_of_claiming_document_exists(self):
        with patch.object(d.requests, 'request', side_effect=d.requests.Timeout('secret URL')):
            with self.assertRaises(d.StorageUnavailable):
                d.exists('supabase://age-proofs/proofs/' + 'a' * 48 + '.pdf')

    def test_download_size_limit(self):
        reply = self.response(b'x' * (d.MAX_FILE + 1))
        with patch.object(d.requests, 'request', return_value=reply):
            with self.assertRaises(d.StorageUnavailable):
                d.read('supabase://age-proofs/proofs/' + 'a' * 48 + '.pdf')
        reply.close.assert_called_once()

    def test_upload_limits(self):
        with patch.object(d.requests, 'request') as request:
            for content, suffix in ((b'', '.pdf'), (b'x' * (d.MAX_FILE + 1), '.pdf'), (b'x', '.exe')):
                with self.assertRaises(ValueError):
                    d.save(content, suffix)
            request.assert_not_called()

    def test_cleanup_uses_private_delete(self):
        with patch.object(d.requests, 'request', return_value=self.response()) as request:
            d.delete('supabase://age-proofs/proofs/' + 'a' * 48 + '.pdf')
        self.assertEqual(request.call_args.args[0], 'DELETE')
        self.assertEqual(request.call_args.kwargs['json'], {'prefixes': ['proofs/' + 'a' * 48 + '.pdf']})

    def test_public_bucket_fails_closed(self):
        reply = self.response()
        reply.json.return_value = {'id': 'age-proofs', 'public': True}
        with patch.object(d.requests, 'request', return_value=reply):
            with self.assertRaises(d.StorageUnavailable):
                d.verify_private_bucket()

    def test_private_bucket_is_accepted(self):
        reply = self.response()
        reply.json.return_value = {'id': 'age-proofs', 'public': False}
        with patch.object(d.requests, 'request', return_value=reply):
            d.verify_private_bucket()

    def test_local_default_survives_adapter_change(self):
        with patch.dict(os.environ, {'DOCUMENT_STORAGE': 'local'}), tempfile.TemporaryDirectory() as folder:
            path = d.save(b'proof', '.pdf', local_path=Path(folder) / 'age.pdf')
            self.assertTrue(d.exists(path))
            self.assertEqual(d.read(path), b'proof')
            d.delete(path)
            self.assertFalse(d.exists(path))


class DatabaseTests(unittest.TestCase):
    def test_hosted_connection_enforces_ssl_private_schema_and_timezone(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://example/database', 'DATABASE_SCHEMA': 'sewasetu'}):
            with patch.object(runtime_db.psycopg2, 'connect') as connect:
                runtime_db.connect(services.config)
        self.assertEqual(connect.call_args.kwargs['sslmode'], 'require')
        self.assertEqual(connect.call_args.kwargs['options'], '-c search_path=sewasetu -c timezone=Asia/Kolkata')

    def test_invalid_schema_is_rejected(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://example/database', 'DATABASE_SCHEMA': 'public;SELECT 1'}):
            with patch.object(runtime_db.psycopg2, 'connect') as connect:
                with self.assertRaises(ValueError):
                    runtime_db.connect(services.config)
                connect.assert_not_called()

    def test_ini_default_is_preserved(self):
        with patch.dict(os.environ):
            os.environ.pop('DATABASE_URL', None)
            with patch.object(runtime_db.psycopg2, 'connect') as connect:
                runtime_db.connect(services.config)
        self.assertEqual(connect.call_args.kwargs['host'], services.config.get('database', 'host'))


if __name__ == '__main__':
    unittest.main()
