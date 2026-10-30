"""stdlib unittest suite; integration tests use an isolated temporary DB schema.

Run in the development app container: python -m unittest discover -s tests -v
"""
import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import psycopg2
from psycopg2 import sql
import services as s


def data(**kw):
    result = dict(applicant_name="  Test Citizen  ", dob="01/01/1950", village="Test Village",
                  block="Sonari", bank_account="1234-5678 9012", ifsc="sbin0003077")
    result.update(kw)
    return result


class ValidationTests(unittest.TestCase):
    def test_fixture_cleanup_refuses_a_non_test_schema(self):
        from types import SimpleNamespace
        with patch.object(s, 'transaction') as transaction:
            cur = transaction.return_value.__enter__.return_value
            cur.fetchone.return_value = ('public',)
            with self.assertRaisesRegex(RuntimeError, 'Refusing fixture cleanup'):
                IntegrationTests.setUp(SimpleNamespace(schema='stage2_test_guard'))
            self.assertEqual(cur.execute.call_count, 1)
            self.assertEqual(cur.execute.call_args.args[0], 'SELECT current_schema()')

    def setUp(self):
        self.clock = patch.object(s, 'now_ist', return_value=datetime(2026, 10, 27, 12))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_normalization_and_existing_optional_fields(self):
        errors, cleaned = s.validate_application(data(), '/proof.pdf')
        self.assertEqual(errors, [])
        self.assertEqual(cleaned['applicant_name'], 'Test Citizen')
        self.assertEqual(cleaned['bank_account'], '123456789012')
        self.assertEqual(cleaned['ifsc'], 'SBIN0003077')
        self.assertEqual(cleaned['husband_employer'], '')

    def test_age_boundary(self):
        self.assertFalse(s.validate_application(data(dob='27/10/1966'), '/proof')[0])
        self.assertTrue(s.validate_application(data(dob='28/10/1966'), '/proof')[0])

    def test_leap_day_age(self):
        self.assertEqual(s.age_on(date(1964, 2, 29), date(2024, 2, 28)), 59)
        self.assertEqual(s.age_on(date(1964, 2, 29), date(2024, 2, 29)), 60)

    def test_invalid_dob(self):
        for value in ['31/02/1950', '1950-01-01', '', None]:
            with self.subTest(value=value):
                self.assertTrue(s.validate_application(data(dob=value), '/proof')[0])

    def test_required_fields(self):
        for key in ['applicant_name', 'village', 'block', 'bank_account']:
            with self.subTest(key=key):
                self.assertTrue(s.validate_application(data(**{key: ''}), '/proof')[0])

    def test_document_required(self):
        self.assertIn('age proof document is required', s.validate_application(data(), '')[0])

    def test_blocks_preserved(self):
        self.assertEqual(s.BLOCKS, ['Sonari', 'Rajapara', 'Dhemaji Pathar', 'Borgaon', 'Namti', 'Khelua'])
        self.assertTrue(s.validate_application(data(block='Unknown'), '/proof')[0])

    def test_bank_length(self):
        for value in ['12345678', '1'*19, 'abc']:
            self.assertTrue(s.validate_application(data(bank_account=value), '/proof')[0])

    def test_ifsc_optional_but_validated_when_present(self):
        self.assertFalse(s.validate_application(data(ifsc=''), '/proof')[0])
        self.assertTrue(s.validate_application(data(ifsc='invalid'), '/proof')[0])

    def test_deadline_exactly_preserved(self):
        self.assertEqual(s.SCHEME_DEADLINE, datetime(2026, 10, 31, 23, 59))
        self.assertEqual(s.SLA_DAYS, 15)
        with patch.object(s, 'now_ist', return_value=s.SCHEME_DEADLINE):
            self.assertFalse(s.validate_application(data(), '/proof')[0])
        with patch.object(s, 'now_ist', return_value=s.SCHEME_DEADLINE + timedelta(microseconds=1)):
            self.assertIn('the application window has closed', s.validate_application(data(), '/proof')[0])

    def test_decision_inputs_rejected_before_database(self):
        with patch.object(s, 'get_db', side_effect=AssertionError('must not connect')):
            for status, actor, reason in [('BAD', 'admin', 'reason'), ('APPROVED', '', 'reason'),
                                          ('REJECTED', 'admin', '  '), ('APPROVED', 'admin', 'x'*501)]:
                with self.subTest(status=status, actor=actor, reason_length=len(reason)):
                    with self.assertRaises(ValueError):
                        s.decide_application(1, status, actor, reason)


@unittest.skipUnless(os.environ.get('RUN_DB_TESTS') == '1', 'set RUN_DB_TESTS=1 in isolated development container')
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_db = s.get_db
        cls.schema = 'stage2_test_' + uuid.uuid4().hex
        conn = cls.original_db()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(cls.schema)))
                    cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(cls.schema)))
                    cur.execute((Path(s.BASE_DIR) / 'schema.sql').read_text())
        finally:
            conn.close()

        def test_db():
            conn = cls.original_db()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(cls.schema)))
            return conn

        cls.db_patch = patch.object(s, 'get_db', side_effect=test_db)
        cls.db_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.db_patch.stop()
        conn = cls.original_db()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))
        finally:
            conn.close()

    def setUp(self):
        with s.transaction() as cur:
            cur.execute('SELECT current_schema()')
            if cur.fetchone()[0] != self.schema:
                raise RuntimeError('Refusing fixture cleanup outside this test class temporary schema')
            cur.execute('TRUNCATE applications, portal_users, audit_log RESTART IDENTITY CASCADE')
        self.clock = patch.object(s, 'now_ist', return_value=datetime(2026, 10, 27, 12))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def submit(self, mobile='9900000001'):
        return s.submit_application(mobile, data(), '/synthetic-proof.pdf')[0]

    def query(self, query, params=()):
        with s.transaction() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def race(self, funcs):
        barrier = threading.Barrier(len(funcs))
        def run(fn):
            barrier.wait(timeout=10)
            return fn()
        with ThreadPoolExecutor(max_workers=len(funcs)) as pool:
            return list(pool.map(run, funcs))

    def test_submission_and_ownership(self):
        app_id = self.submit()
        self.assertEqual(s.get_latest_application_id('9900000001'), app_id)
        self.assertEqual(s.get_citizen_application(app_id, '9900000001')[8], 'PENDING')
        self.assertIsNone(s.get_citizen_application(app_id, '9900000002'))
        self.assertIsNone(s.get_citizen_application(app_id, None))
        self.assertIsNone(s.withdraw_pending_application(app_id, '9900000002'))
        self.assertEqual(s.get_audit(app_id)[0][1:3], ('SUBMIT', 'applicant:9900000001'))

    def test_rejected_and_withdrawn_can_reapply(self):
        for status in ['WITHDRAWN', 'REJECTED']:
            app_id = self.submit()
            if status == 'WITHDRAWN':
                self.assertTrue(s.withdraw_pending_application(app_id, '9900000001'))
            else:
                self.assertTrue(s.decide_application(app_id, status, 'officer-one', 'Evidence checked'))
        self.submit()
        self.assertEqual(self.query('SELECT count(*) FROM applications')[0][0], 3)
        self.assertEqual(self.query('SELECT count(*) FROM portal_users')[0][0], 1)

    def test_concurrent_submissions(self):
        def attempt():
            try:
                return s.submit_application('9900000001', data(), '/proof')
            except s.DuplicateApplication:
                return None
        results = self.race([attempt, attempt])
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(self.query('SELECT count(*) FROM applications')[0][0], 1)
        self.assertEqual(self.query('SELECT count(*) FROM portal_users')[0][0], 1)
        self.assertEqual(self.query('SELECT count(*) FROM audit_log')[0][0], 1)

    def test_direct_database_duplicate_protection(self):
        self.submit()
        _, cleaned = s.validate_application(data(), '/proof')
        with self.assertRaises(psycopg2.errors.UniqueViolation):
            with s.transaction() as cur:
                s.create_application(cur, '9900000001', cleaned)
        app_no = self.query('SELECT application_no FROM applications')[0][0]
        with self.assertRaises(psycopg2.errors.UniqueViolation):
            with s.transaction() as cur:
                cur.execute('INSERT INTO applications(application_no,mobile,status) VALUES (%s,%s,%s)', (app_no, '9900000002', 'PENDING'))

    def test_application_number_collision_retried(self):
        with patch.object(s, 'new_application_no', return_value='SSP26COLLISION'):
            self.submit()
        with patch.object(s, 'new_application_no', side_effect=['SSP26COLLISION', 'SSP26NEWNUMBER']):
            app_id = self.submit('9900000002')
        self.assertEqual(s.get_citizen_application(app_id, '9900000002')[0], 'SSP26NEWNUMBER')

    def test_simultaneous_different_mobile_number_collision(self):
        barrier = threading.Barrier(2)
        counter = threading.local()
        def number():
            if not getattr(counter, 'attempted', False):
                counter.attempted = True
                barrier.wait(timeout=10)
                return 'SSP26COLLISION'
            return 'SSP26' + uuid.uuid4().hex[:12]
        with patch.object(s, 'new_application_no', side_effect=number):
            results = self.race([lambda: self.submit('9900000001'), lambda: self.submit('9900000002')])
        self.assertEqual(len(set(results)), 2)

    def test_concurrent_decisions(self):
        app_id = self.submit()
        results = self.race([lambda: s.decide_application(app_id, 'APPROVED', 'alice', 'Alice approved'),
                             lambda: s.decide_application(app_id, 'REJECTED', 'bob', 'Bob rejected')])
        self.assertEqual(sum(r is not None for r in results), 1)
        row = s.get_officer_application(app_id, 'alice')
        entries = s.get_audit(app_id)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[-1][1], row[11])
        self.assertEqual(entries[-1][2], 'admin:' + row[14])
        self.assertEqual(entries[-1][3], {'alice': 'Alice approved', 'bob': 'Bob rejected'}[row[14]])

    def test_decision_vs_withdrawal(self):
        app_id = self.submit()
        results = self.race([lambda: s.decide_application(app_id, 'APPROVED', 'alice', 'Checked'),
                             lambda: s.withdraw_pending_application(app_id, '9900000001')])
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(len(s.get_audit(app_id)), 2)

    def test_submission_audit_failure_rolls_back_everything(self):
        with patch.object(s, 'write_audit', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.submit()
        for table in ['applications', 'portal_users', 'audit_log']:
            self.assertEqual(self.query('SELECT count(*) FROM ' + table)[0][0], 0)

    def test_decision_audit_failure_rolls_back(self):
        app_id = self.submit()
        with patch.object(s, 'write_audit', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                s.decide_application(app_id, 'APPROVED', 'alice', 'Checked')
        self.assertEqual(s.get_citizen_application(app_id, '9900000001')[8], 'PENDING')
        self.assertEqual(len(s.get_audit(app_id)), 1)

    def test_withdrawal_audit_failure_rolls_back(self):
        app_id = self.submit()
        with patch.object(s, 'write_audit', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                s.withdraw_pending_application(app_id, '9900000001')
        self.assertEqual(s.get_citizen_application(app_id, '9900000001')[8], 'PENDING')

    def test_invalid_application_inserts_nothing(self):
        with self.assertRaises(s.ValidationError):
            s.submit_application('9900000001', data(dob='01/01/2010'), '')
        self.assertEqual(self.query('SELECT count(*) FROM applications')[0][0], 0)

    def test_deadline_rejects_submission_but_not_followup(self):
        app_id = self.submit()
        with patch.object(s, 'now_ist', return_value=datetime(2026, 11, 1)):
            with self.assertRaises(s.ValidationError):
                self.submit('9900000002')
            self.assertIsNotNone(s.get_citizen_application(app_id, '9900000001'))
            self.assertTrue(s.decide_application(app_id, 'APPROVED', 'alice', 'Verified after window'))

    def test_nonpending_cannot_be_decided_or_withdrawn(self):
        app_id = self.submit()
        s.decide_application(app_id, 'APPROVED', 'alice', 'Checked')
        self.assertIsNone(s.decide_application(app_id, 'REJECTED', 'bob', 'Too late'))
        self.assertIsNone(s.withdraw_pending_application(app_id, '9900000001'))
        self.assertEqual(len(s.get_audit(app_id)), 2)

    def test_migration_is_repeatable(self):
        migration = (Path(s.BASE_DIR) / 'migrations/001_application_uniqueness.sql').read_text()
        for _ in range(2):
            with s.transaction() as cur:
                cur.execute(migration)
        self.submit()
        with self.assertRaises(s.DuplicateApplication):
            self.submit()

    def test_web_decision_requires_reason_and_ignores_forged_actor(self):
        import app as portal
        from flask import session
        app_id = self.submit()
        with portal.app.test_request_context('/admin/approve', method='POST', data={'note': '  ', 'actor': 'mallory'}):
            session['admin'] = True
            session['admin_user'] = 'alice'
            self.assertEqual(portal.admin_approve(app_id).status_code, 302)
        self.assertEqual(s.get_citizen_application(app_id, '9900000001')[8], 'PENDING')
        with portal.app.test_request_context('/admin/approve', method='POST', data={'note': 'Verified', 'actor': 'mallory'}):
            session['admin'] = True
            session['admin_user'] = 'alice'
            portal.admin_approve(app_id)
        self.assertEqual(s.get_audit(app_id)[-1][2:], ('admin:alice', 'Verified'))

    def test_web_officer_boundary(self):
        import app as portal
        from flask import session
        from werkzeug.exceptions import Forbidden
        app_id = self.submit()
        with portal.app.test_request_context('/admin/approve', method='POST', data={'note': 'Forged'}):
            session['portal_mobile'] = '9900000001'
            with self.assertRaises(Forbidden):
                portal.admin_approve(app_id)
        self.assertEqual(s.get_citizen_application(app_id, '9900000001')[8], 'PENDING')


if __name__ == '__main__':
    unittest.main()
