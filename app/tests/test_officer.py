"""Officer operations against an isolated temporary schema in development Postgres."""
import hashlib
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import officer as o
import services as s
from officer_auth import Officer
import test_services as support


@unittest.skipUnless(os.environ.get('RUN_DB_TESTS') == '1', 'requires isolated development Postgres')
class OfficerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.IntegrationTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        support.IntegrationTests.tearDownClass.__func__(cls)

    query = support.IntegrationTests.query
    race = support.IntegrationTests.race

    def setUp(self):
        support.IntegrationTests.setUp(self)
        with s.transaction() as cur:
            cur.execute('TRUNCATE oauth_agent_sessions CASCADE')
            for sid, who in [('session-alice', 'alice'), ('session-bob', 'bob')]:
                cur.execute('INSERT INTO oauth_agent_sessions(id,subject,client_id,audience,expires_at) VALUES (%s,%s,%s,%s,%s)',
                            (sid, 'officer:'+who, 'client', o.RESOURCE, int(time.time())+28800))
        self.alice = Officer('officer:alice', 'session-alice', 'client', int(time.time())+1800)
        self.bob = Officer('officer:bob', 'session-bob', 'client', int(time.time())+1800)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proof = Path(self.temp.name) / 'proof.pdf'
        self.proof.write_bytes(b'%PDF-1.4 synthetic fixture')
        original_get = s.config.get
        getter = patch.object(s.config, 'get', side_effect=lambda section, name, *a, **kw:
                              self.temp.name if (section, name) == ('app', 'upload_dir') else original_get(section, name, *a, **kw))
        getter.start()
        self.addCleanup(getter.stop)
        self.mobile = 9900000000

    def case(self, block='Sonari'):
        self.mobile += 1
        return s.submit_application(str(self.mobile), support.data(block=block), str(self.proof))[0]

    def proposal(self, actor, app_id, decision='APPROVED', reason='Evidence reviewed'):
        view = o.inspect_case(actor, app_id)
        proposed = o.decide(actor, app_id, decision, reason, view['review_token'])
        return view, proposed

    def confirm(self, actor, app_id, view, proposed):
        return o.decide(actor, app_id, proposed['decision'], proposed['reason'], view['review_token'], True, proposed['confirmation_token'])

    def test_queue_summary_and_list_are_scoped_and_masked(self):
        allowed = self.case()
        self.case('Rajapara'); self.case('Namti')
        summary = o.summary(self.alice)
        self.assertEqual(summary['counts_by_status']['PENDING'], 2)
        self.assertEqual(set(summary['pending_by_block']), {'Sonari', 'Rajapara'})
        rows = o.list_cases(self.alice)['applications']
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['application_id'], allowed)
        self.assertNotIn('mobile', rows[0])
        self.assertNotIn('bank_account', rows[0])

    def test_pagination(self):
        for _ in range(21):
            self.case()
        first = o.list_cases(self.alice)
        second = o.list_cases(self.alice, after_id=first['next_after_id'])
        self.assertEqual(len(first['applications']), 20)
        self.assertEqual(len(second['applications']), 1)
        self.assertNotEqual(first['applications'][0]['application_id'], second['applications'][0]['application_id'])

    def test_inspection_and_browser_proof(self):
        app_id = self.case()
        view = o.inspect_case(self.alice, app_id)
        self.assertEqual(view['bank_account_last4'], '9012')
        self.assertNotIn('doc_path', view)
        self.assertNotIn('bank_account', view)
        self.assertTrue(view['audit'][0]['actor'].startswith('applicant:***'))
        self.assertTrue(view['age_proof_available'])
        token = view['age_proof_url'].rsplit('/', 1)[1]
        with self.assertRaises(o.OfficerError):
            with s.transaction() as cur:
                o.resolve_link(cur, token, 'proof', None)
        with self.assertRaises(o.OfficerError):
            with s.transaction() as cur:
                o.resolve_link(cur, token, 'proof', {'subject': 'citizen:9900000001', 'at': int(time.time())})
        with s.transaction() as cur:
            actor, actual, digest = o.resolve_link(cur, token, 'proof', {'subject': self.alice.subject, 'at': int(time.time())})
            self.assertEqual(actual, app_id)
            self.assertEqual(actor.username, 'alice')

    def test_approval_and_authenticated_audit_actor(self):
        app_id = self.case()
        view, proposal = self.proposal(self.alice, app_id)
        self.assertEqual(s.get_officer_application(app_id, 'alice')[11], 'PENDING')
        result = self.confirm(self.alice, app_id, view, proposal)
        self.assertEqual(result['status'], 'APPROVED')
        self.assertEqual(s.get_audit(app_id)[-1][2:], ('admin:alice', 'Evidence reviewed'))

    def test_rejection_with_reason(self):
        app_id = self.case()
        view, proposal = self.proposal(self.bob, app_id, 'REJECTED', 'Proof does not match the applicant')
        result = self.confirm(self.bob, app_id, view, proposal)
        self.assertEqual(result['status'], 'REJECTED')
        self.assertEqual(result['decided_by'], 'bob')

    def test_required_reason(self):
        app_id = self.case()
        view = o.inspect_case(self.alice, app_id)
        for reason in ['', '  ', 'x'*501]:
            with self.assertRaises(o.OfficerError):
                o.decide(self.alice, app_id, 'APPROVED', reason, view['review_token'], True)

    def test_direct_confirmation_without_preview_rejected(self):
        app_id = self.case()
        view = o.inspect_case(self.alice, app_id)
        with self.assertRaises(o.OfficerError):
            o.decide(self.alice, app_id, 'APPROVED', 'Checked', view['review_token'], True, 'forged')

    def test_changed_reason_or_decision_invalidates_confirmation(self):
        app_id = self.case()
        view, proposal = self.proposal(self.alice, app_id)
        for decision, reason in [('REJECTED', proposal['reason']), ('APPROVED', 'Different reason')]:
            with self.assertRaises(o.OfficerError):
                o.decide(self.alice, app_id, decision, reason, view['review_token'], True, proposal['confirmation_token'])

    def test_expired_review(self):
        app_id = self.case()
        view, proposal = self.proposal(self.alice, app_id)
        self.query('UPDATE officer_reviews SET expires_at=0 RETURNING token_hash')
        with self.assertRaises(o.OfficerError):
            self.confirm(self.alice, app_id, view, proposal)

    def test_review_bound_to_actor_session(self):
        app_id = self.case()
        view, proposal = self.proposal(self.alice, app_id)
        with self.assertRaises(o.OfficerError):
            self.confirm(self.bob, app_id, view, proposal)

    def test_expired_and_revoked_officer_session(self):
        app_id = self.case()
        expired = Officer(self.alice.subject, self.alice.session_id, 'client', 0)
        with self.assertRaises(o.OfficerError):
            o.inspect_case(expired, app_id)
        self.query('UPDATE oauth_agent_sessions SET revoked_at=1 RETURNING id')
        with self.assertRaises(o.OfficerError):
            o.summary(self.alice)

    def test_unsupported_block_cannot_be_read_or_decided(self):
        app_id = self.case('Namti')
        with self.assertRaises(o.OfficerError):
            o.inspect_case(self.alice, app_id)
        with self.assertRaises(o.OfficerError):
            o.list_cases(self.alice, block='Namti')
        self.assertIsNone(s.get_officer_application(app_id, 'alice', blocks=('Sonari', 'Rajapara')))
        self.assertIsNone(s.decide_application(app_id, 'APPROVED', 'alice', 'Checked', blocks=('Sonari', 'Rajapara')))
        self.assertEqual(s.get_officer_application(app_id, 'alice')[11], 'PENDING')

    def test_changed_allowlist_blocks_prior_review(self):
        app_id = self.case()
        view, proposal = self.proposal(self.alice, app_id)
        with patch.dict(os.environ, {'CITIZEN_MCP_BLOCKS': 'Rajapara'}):
            with self.assertRaises(o.OfficerError):
                self.confirm(self.alice, app_id, view, proposal)

    def test_competing_decisions_one_winner(self):
        app_id = self.case()
        av, ap = self.proposal(self.alice, app_id)
        bv, bp = self.proposal(self.bob, app_id, 'REJECTED', 'Bob checked the proof')
        def attempt(actor, view, proposed):
            try:
                return self.confirm(actor, app_id, view, proposed)
            except o.OfficerError:
                return None
        results = self.race([lambda: attempt(self.alice, av, ap), lambda: attempt(self.bob, bv, bp)])
        self.assertEqual(sum(r is not None for r in results), 1)
        audit = s.get_audit(app_id)
        self.assertEqual(len(audit), 2)
        winner = next(r for r in results if r)
        self.assertEqual(audit[-1][2:], ('admin:'+winner['decided_by'], winner['reason']))

    def test_all_terminal_statuses_cannot_be_overwritten(self):
        for terminal in ['APPROVED', 'REJECTED', 'WITHDRAWN', 'DEEMED_APPROVED']:
            app_id = self.case()
            view, proposal = self.proposal(self.alice, app_id)
            # Represents another portal channel or the unchanged statutory scheduler.
            self.query('UPDATE applications SET status=%s WHERE id=%s RETURNING id', (terminal, app_id))
            with self.assertRaises(o.OfficerError):
                self.confirm(self.alice, app_id, view, proposal)
            self.assertEqual(s.get_officer_application(app_id, 'alice')[11], terminal)
            self.assertEqual(len(s.get_audit(app_id)), 1)

    def test_withdrawal_race(self):
        app_id = self.case()
        view, proposal = self.proposal(self.alice, app_id)
        number = self.query('SELECT mobile FROM applications WHERE id=%s', (app_id,))[0][0]
        def confirm():
            try:
                return self.confirm(self.alice, app_id, view, proposal)
            except o.OfficerError:
                return None
        results = self.race([confirm, lambda: s.withdraw_pending_application(app_id, number)])
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(len(s.get_audit(app_id)), 2)

    def test_audit_failure_rolls_back_review_and_decision(self):
        app_id = self.case()
        view, proposal = self.proposal(self.alice, app_id)
        with patch.object(s, 'write_audit', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.confirm(self.alice, app_id, view, proposal)
        self.assertEqual(s.get_officer_application(app_id, 'alice')[11], 'PENDING')
        self.assertIsNone(self.query('SELECT consumed_at FROM officer_reviews')[0][0])

    def test_case_and_proof_changes_require_new_review(self):
        app_id = self.case()
        view, proposal = self.proposal(self.alice, app_id)
        self.proof.write_bytes(b'%PDF-1.4 changed proof')
        with self.assertRaises(o.OfficerError):
            self.confirm(self.alice, app_id, view, proposal)

    def test_unsafe_paths_not_served(self):
        self.assertEqual(o.proof_info('/etc/passwd'), (None, None))
        self.assertEqual(o.proof_info(''), (None, None))

    def test_strict_signed_officer_token(self):
        import app as portal
        import jwt
        from oauth import signing_key
        from officer_auth import verify_officer_token
        kid, key = signing_key()
        claims = {'iss': o.ISSUER, 'aud': o.RESOURCE, 'sub': self.alice.subject, 'sid': self.alice.session_id,
                  'client_id': 'client', 'iat': int(time.time()), 'exp': int(time.time())+600,
                  'session_ends': int(time.time())+28800, 'role': 'officer', 'scope': 'officer', 'kind': 'access'}
        def token(values):
            return jwt.encode(values, key, algorithm='RS256', headers={'kid': kid})
        self.assertIsNotNone(verify_officer_token(token(claims)))
        for changes in [{'role': 'citizen'}, {'scope': 'citizen'}, {'aud': o.ISSUER+'/mcp/citizen'},
                        {'iss': 'https://wrong.invalid'}, {'sub': 'citizen:9900000001'},
                        {'exp': 1}, {'session_ends': 1}, {'kind': 'program'}, {'sid': 'wrong'}, {'client_id': 'wrong'}]:
            with self.subTest(changes=changes):
                self.assertIsNone(verify_officer_token(token({**claims, **changes})))
        for missing in ['sid', 'exp', 'session_ends']:
            altered = dict(claims); del altered[missing]
            self.assertIsNone(verify_officer_token(token(altered)))
