import io
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fpdf import FPDF
from PIL import Image
import citizen as c
import services as s
from citizen_auth import Citizen
import test_services as support
from test_services import data


def proof():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', size=12)
    pdf.cell(0, 10, 'SYNTHETIC TEST DOCUMENT')
    return bytes(pdf.output())


class DocumentTests(unittest.TestCase):
    def test_public_configuration_fails_closed(self):
        from citizen_auth import validate_public_configuration
        validate_public_configuration('http://localhost:8000', '', '1', '')
        validate_public_configuration('https://portal.example', 'x'*64, None, 'private-password')
        for issuer, secret, console, password in [('http://portal.example', 'x'*64, None, 'private'),
                ('https://portal.example', '', None, 'private'),
                ('https://portal.example', 'x'*64, '1', 'private'),
                ('https://portal.example', 'x'*64, None, 'change-me-before-deploying')]:
            with self.assertRaises(RuntimeError):
                validate_public_configuration(issuer, secret, console, password)

    def test_valid_pdf(self):
        self.assertEqual(c.validate_document('proof.pdf', proof()), '.pdf')

    def test_valid_png_and_jpeg(self):
        for fmt, ext in [('PNG', '.png'), ('JPEG', '.jpg')]:
            buffer = io.BytesIO()
            Image.new('RGB', (10, 10), 'white').save(buffer, format=fmt)
            self.assertEqual(c.validate_document('proof' + ext, buffer.getvalue()), ext)

    def test_invalid_empty_oversize_and_extension(self):
        for name, contents in [('a.pdf', b''), ('a.pdf', b'not a PDF'), ('a.pdf', b'x'*(c.MAX_FILE+1)),
                               ('a.exe', proof()), ('a.png', proof())]:
            with self.subTest(name=name, size=len(contents)):
                with self.assertRaises(c.CitizenError):
                    c.validate_document(name, contents)

    def test_invalid_allowlist_fails_closed(self):
        for value in ['', 'Sonari,Unknown']:
            with patch.dict(os.environ, {'CITIZEN_MCP_BLOCKS': value}):
                with self.assertRaises(RuntimeError):
                    c.supported_blocks()


@unittest.skipUnless(os.environ.get('RUN_DB_TESTS') == '1', 'requires isolated development Postgres')
class CitizenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.IntegrationTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        support.IntegrationTests.tearDownClass.__func__(cls)

    def setUp(self):
        support.IntegrationTests.setUp(self)
        with s.transaction() as cur:
            cur.execute('TRUNCATE oauth_agent_sessions CASCADE')
            cur.execute('INSERT INTO oauth_agent_sessions(id,subject,client_id,audience,expires_at) VALUES (%s,%s,%s,%s,%s)',
                        ('session-a', 'citizen:9900000001', 'client-a', c.RESOURCE, int(time.time())+7200))
        self.actor = Citizen('citizen:9900000001', 'session-a', 'client-a', int(time.time())+1200)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'proof.pdf'
        self.path.write_bytes(proof())

    query = support.IntegrationTests.query

    def prepared(self, **kw):
        result = c.prepare(self.actor, data(**kw))
        with s.transaction() as cur:
            cur.execute('UPDATE citizen_drafts SET doc_path=%s,revision=revision+1 WHERE id=%s', (str(self.path), result['draft_id']))
        return c.prepare(self.actor, draft_id=result['draft_id'])

    def test_successful_submission_and_idempotent_retry(self):
        p = self.prepared()
        self.assertTrue(p['ready_to_submit'])
        with patch('app.send_sms'):
            result = c.submit(self.actor, p['draft_id'], p['revision'], True)
            again = c.submit(self.actor, p['draft_id'], p['revision'], True)
        self.assertEqual(result['application_id'], again['application_id'])
        self.assertTrue(again['already_submitted'])
        self.assertEqual(self.query('SELECT count(*) FROM applications')[0][0], 1)
        self.assertEqual(self.query('SELECT count(*) FROM audit_log')[0][0], 1)
        self.assertIsNotNone(self.query('SELECT declaration_accepted_at FROM citizen_drafts')[0][0])

    def test_declaration_required_and_stale_preview(self):
        p = self.prepared()
        for revision, accepted in [(p['revision'], False), (p['revision']-1, True)]:
            with self.assertRaises(c.CitizenError):
                c.submit(self.actor, p['draft_id'], revision, accepted)
        self.assertEqual(self.query('SELECT count(*) FROM applications')[0][0], 0)

    def test_invalid_details(self):
        for details in [{'mobile': '9900000002'}, {'bank_account': 123}, {'village': 'x'*101}]:
            with self.assertRaises(c.CitizenError):
                c.prepare(self.actor, details)
        p = self.prepared(dob='01/01/2010')
        self.assertFalse(p['ready_to_submit'])
        with self.assertRaises(c.CitizenError):
            c.submit(self.actor, p['draft_id'], p['revision'], True)

    def test_unsupported_block(self):
        p = self.prepared(block='Namti')
        self.assertFalse(p['ready_to_submit'])
        with self.assertRaises(c.CitizenError) as caught:
            c.submit(self.actor, p['draft_id'], p['revision'], True)
        self.assertEqual(caught.exception.code, 'unsupported_block')

    def test_missing_document(self):
        p = c.prepare(self.actor, data())
        with self.assertRaises(c.CitizenError):
            c.submit(self.actor, p['draft_id'], p['revision'], True)

    def test_same_mobile_different_session_cannot_read_draft(self):
        p = self.prepared()
        with s.transaction() as cur:
            cur.execute('INSERT INTO oauth_agent_sessions(id,subject,client_id,audience,expires_at) VALUES (%s,%s,%s,%s,%s)',
                        ('session-b', self.actor.subject, 'client-a', c.RESOURCE, int(time.time())+7200))
        other = Citizen(self.actor.subject, 'session-b', 'client-a', int(time.time())+1200)
        with self.assertRaises(c.CitizenError):
            c.prepare(other, draft_id=p['draft_id'])

    def test_concurrent_same_draft_retries(self):
        p = self.prepared()
        with patch('app.send_sms'):
            with ThreadPoolExecutor(max_workers=2) as pool:
                result = list(pool.map(lambda _: c.submit(self.actor, p['draft_id'], p['revision'], True), range(2)))
        self.assertEqual(result[0]['application_id'], result[1]['application_id'])
        self.assertEqual(sum(r['already_submitted'] for r in result), 1)

    def test_different_draft_duplicate_submission(self):
        p, q = self.prepared(), self.prepared()
        with patch('app.send_sms'):
            c.submit(self.actor, p['draft_id'], p['revision'], True)
        with self.assertRaises(c.CitizenError) as caught:
            c.submit(self.actor, q['draft_id'], q['revision'], True)
        self.assertEqual(caught.exception.code, 'duplicate_application')

    def test_expired_and_revoked_sessions(self):
        p = self.prepared()
        expired = Citizen(self.actor.subject, self.actor.session_id, self.actor.client_id, int(time.time())-1)
        with self.assertRaises(c.CitizenError):
            c.submit(expired, p['draft_id'], p['revision'], True)
        with s.transaction() as cur:
            cur.execute('UPDATE oauth_agent_sessions SET revoked_at=%s', (int(time.time()),))
        with self.assertRaises(c.CitizenError):
            c.prepare(self.actor)

    def test_expired_draft(self):
        p = self.prepared()
        with s.transaction() as cur:
            cur.execute('UPDATE citizen_drafts SET expires_at=0')
        with self.assertRaises(c.CitizenError):
            c.submit(self.actor, p['draft_id'], p['revision'], True)

    def test_upload_link_browser_ownership_and_expiry(self):
        p = self.prepared()
        token = p['upload_url'].rsplit('/', 1)[1]
        for browser in [None, {'subject': 'citizen:9900000002', 'at': int(time.time())}]:
            with self.assertRaises(c.CitizenError):
                with s.transaction() as cur:
                    c.resolve_link(cur, token, 'upload', browser)
        with s.transaction() as cur:
            c.resolve_link(cur, token, 'upload', {'subject': self.actor.subject, 'at': int(time.time())})
            cur.execute('UPDATE citizen_links SET expires_at=0')
        with self.assertRaises(c.CitizenError):
            with s.transaction() as cur:
                c.resolve_link(cur, token, 'upload', {'subject': self.actor.subject, 'at': int(time.time())})

    def test_status_and_withdrawal_ownership(self):
        p = self.prepared()
        with patch('app.send_sms'):
            result = c.submit(self.actor, p['draft_id'], p['revision'], True)
        app_id = result['application_id']
        self.assertEqual(len(c.my_applications(self.actor)['applications']), 1)
        self.assertFalse(c.withdraw(self.actor, app_id, False)['ok'])
        with s.transaction() as cur:
            cur.execute('UPDATE applications SET mobile=%s WHERE id=%s', ('9900000002', app_id))
        self.assertEqual(c.my_applications(self.actor)['applications'], [])
        with self.assertRaises(c.CitizenError):
            c.withdraw(self.actor, app_id, True)

    def test_changed_allowlist_blocks_existing_draft(self):
        p = self.prepared()
        with patch.dict(os.environ, {'CITIZEN_MCP_BLOCKS': 'Rajapara'}):
            with self.assertRaises(c.CitizenError):
                c.submit(self.actor, p['draft_id'], p['revision'], True)

    def test_failed_shared_submission_does_not_mark_draft(self):
        p = self.prepared()
        with patch.object(s, 'write_audit', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                c.submit(self.actor, p['draft_id'], p['revision'], True)
        self.assertIsNone(self.query('SELECT application_id FROM citizen_drafts')[0][0])
        self.assertEqual(self.query('SELECT count(*) FROM applications')[0][0], 0)

    def test_signed_token_claims_and_expiry(self):
        import jwt
        from oauth import signing_key
        from citizen_auth import verify_citizen_token
        kid, key = signing_key()
        claims = {'iss': c.ISSUER, 'aud': c.RESOURCE, 'sub': self.actor.subject, 'sid': self.actor.session_id,
                  'client_id': self.actor.client_id, 'iat': int(time.time()), 'exp': int(time.time())+600,
                  'session_ends': int(time.time())+7200, 'role': 'citizen', 'scope': 'citizen', 'kind': 'access'}
        def token(values):
            return jwt.encode(values, key, algorithm='RS256', headers={'kid': kid})
        self.assertIsNotNone(verify_citizen_token(token(claims)))
        for changes in [{'role': 'officer'}, {'scope': 'officer'}, {'aud': c.ISSUER}, {'iss': 'https://wrong.invalid'},
                        {'exp': int(time.time())-1}, {'session_ends': 0}, {'sub': 'citizen:other'},
                        {'kind': 'program'}, {'sid': 'another-session'}, {'client_id': 'another-client'}]:
            with self.subTest(changes=changes):
                self.assertIsNone(verify_citizen_token(token({**claims, **changes})))
        for required in ['exp', 'sid', 'session_ends']:
            altered = dict(claims)
            del altered[required]
            self.assertIsNone(verify_citizen_token(token(altered)))

    def test_concurrent_initial_signing_keys(self):
        import app as portal
        import oauth
        with patch.object(oauth, '_KEY_CACHE', {}), patch.object(portal, 'get_db', side_effect=s.get_db):
            with ThreadPoolExecutor(max_workers=2) as pool:
                keys = list(pool.map(lambda _: oauth.signing_key()[0], range(2)))
            self.assertEqual(len(set(keys)), 1)
            self.assertEqual(self.query('SELECT count(*) FROM oauth_keys')[0][0], 1)
