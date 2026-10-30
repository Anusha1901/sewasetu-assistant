"""Public evidence contract: no live records, credentials, mutations or invented passes."""
import copy
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from werkzeug.test import Client
from werkzeug.wrappers import Response
import app as portal
import evaluation_dashboard as evaluation


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.client = Client(portal.app, Response, use_cookies=False)
        self.data, self.digest = evaluation.load_evidence()

    def test_public_page_requires_no_authentication(self):
        response = self.client.get('/eval-dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Set-Cookie', response.headers)
        self.assertIn('Pension access', response.text)

    def test_public_json_is_exact_bundled_snapshot(self):
        response = self.client.get('/eval-dashboard/evidence.json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, self.data)

    def test_snapshot_hash_is_the_file_hash(self):
        self.assertEqual(self.digest, hashlib.sha256(evaluation.EVIDENCE.read_bytes()).hexdigest())
        self.assertIn(self.digest, self.client.get('/eval-dashboard').text)

    def test_summary_totals_are_derived_from_assertions(self):
        self.assertEqual(len(self.data['checks']), 376)
        self.assertEqual(sum(r['scope'] == 'LOCAL' for r in self.data['checks']), 275)
        self.assertEqual(sum(r['scope'] == 'LIVE' for r in self.data['checks']), 101)
        self.assertEqual(sum(r['status'] == 'FAIL' for r in self.data['checks']), 0)

    def test_every_claimed_scenario_has_recorded_evidence(self):
        lookup = {r['id']: r for r in self.data['checks']}
        for scenario in self.data['scenarios']:
            if scenario['status'] == 'PASS':
                self.assertTrue(scenario['check_ids'])
                self.assertTrue(all(lookup[ref]['status'] == 'PASS' for ref in scenario['check_ids']))

    def test_untested_scenarios_are_explicit_and_not_counted(self):
        untested = [r for r in self.data['scenarios'] if r['status'] == 'NOT TESTED']
        self.assertEqual(len(untested), 3)
        self.assertTrue(all(not r['check_ids'] for r in untested))
        self.assertIn('Claude Code', self.client.get('/eval-dashboard').text)

    def test_dashboard_does_not_open_a_database_connection(self):
        with patch('services.get_db', side_effect=AssertionError('Dashboard must not query private records')):
            self.assertEqual(self.client.get('/eval-dashboard').status_code, 200)
            self.assertEqual(self.client.get('/eval-dashboard/evidence.json').status_code, 200)

    def test_authenticated_browser_data_is_never_rendered(self):
        serializer = portal.app.session_interface.get_signing_serializer(portal.app)
        cookie = serializer.dumps({'admin': True, 'portal_mobile': '9999991234',
                                   'form_data': {'bank_account': 'PRIVATE-BANK-CANARY'}})
        response = self.client.get('/eval-dashboard', headers={'Cookie': 'session=' + cookie})
        self.assertNotIn('9999991234', response.text)
        self.assertNotIn('PRIVATE-BANK-CANARY', response.text)

    def test_public_snapshot_has_no_authentication_material_or_private_paths(self):
        text = self.client.get('/eval-dashboard/evidence.json').text
        for pattern in [r'eyJ[\w-]{15,}\.[\w-]{20,}\.[\w-]{20,}', r'-----BEGIN .*PRIVATE KEY',
                        r'gh[pousr]_[A-Za-z0-9]{30,}', r'(?:postgresql|postgres)://',
                        r'"(?:mobile|bank_account|password|access_token|refresh_token|doc_path)"\s*:',
                        r'https?://[^\s"]+/(?:citizen|officer)/(?:upload|proof|ack|finish)/[\w-]+']:
            self.assertIsNone(re.search(pattern, text))

    def test_only_allowlisted_synthetic_cases_are_present(self):
        self.assertEqual({r['id'] for r in self.data['cases']}, {100011, 100012, 100013, 100014})
        self.assertTrue(all('Synthetic' in r['name'] for r in self.data['cases']))
        for r in self.data['cases']:
            self.assertEqual(set(r), {'id','number','name','age','village','block','status','mode','voice','goal','database_expectation','actual'})

    def test_query_parameters_cannot_select_database_records_or_files(self):
        original = self.client.get('/eval-dashboard/evidence.json')
        for query in ['?application_id=1', '?path=../../config/app.ini', '?file=deploy/secrets/render.env']:
            self.assertEqual(self.client.get('/eval-dashboard/evidence.json' + query).data, original.data)

    def test_evidence_endpoints_cannot_mutate_state(self):
        for path in ['/eval-dashboard', '/eval-dashboard/evidence.json']:
            self.assertEqual(self.client.post(path, data={'status':'APPROVED'}).status_code, 405)
            self.assertEqual(self.client.delete(path).status_code, 405)

    def test_headers_restrict_scripts_frames_and_connections(self):
        response = self.client.get('/eval-dashboard')
        self.assertIn("default-src 'none'", response.headers['Content-Security-Policy'])
        self.assertIn("connect-src 'none'", response.headers['Content-Security-Policy'])
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')

    def test_client_data_is_html_escaped(self):
        altered = copy.deepcopy(self.data)
        altered['cases'][0]['name'] = '<script>alert("canary")</script>'
        with patch.object(evaluation, 'load_evidence', return_value=(altered, self.digest)):
            page = self.client.get('/eval-dashboard').text
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>alert', page)

    def test_endpoints_and_block_restrictions_are_clear(self):
        page = self.client.get('/eval-dashboard').text
        for text in ['/mcp/citizen', '/mcp/officer', 'Streamable HTTP', 'Sonari and Rajapara only']:
            self.assertIn(text, page)

    def test_no_external_assets_or_telemetry_are_loaded(self):
        page = self.client.get('/eval-dashboard').text
        self.assertNotRegex(page, r'(?:src|href)="https?://')
        javascript = (Path(portal.BASE_DIR) / 'static/eval-dashboard.js').read_text()
        self.assertNotIn('fetch(', javascript)
        self.assertNotIn('innerHTML', javascript)

    def test_mobile_viewport_and_keyboard_navigation_are_present(self):
        page = self.client.get('/eval-dashboard').text
        self.assertIn('name="viewport"', page)
        self.assertIn('Skip to evaluation results', page)
        self.assertIn('aria-live="polite"', page)
        self.assertIn('<details', page)

    def test_transcript_and_sdk_fixtures_are_not_conflated(self):
        page = self.client.get('/eval-dashboard').text
        self.assertIn('verbatim excerpt', page)
        self.assertIn('not a complete transcript', page)
        self.assertIn('not three independent AI conversations', page)
        self.assertIn('I accept the declaration for this test application. Submit revision 2.', page)

    def test_scheme_deadline_and_sla_remain_unchanged(self):
        page = self.client.get('/eval-dashboard').text
        self.assertIn('31 October 2026, 23:59 IST', page)
        self.assertIn('15-day deemed approval', page)
        self.assertEqual(portal.SCHEME_DEADLINE.isoformat(), '2026-10-31T23:59:00')
        self.assertEqual(portal.MIN_AGE, 60)

    def test_no_cookie_or_identity_changes_on_json_head(self):
        response = self.client.head('/eval-dashboard/evidence.json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'')
        self.assertNotIn('Set-Cookie', response.headers)


if __name__ == '__main__':
    unittest.main()
