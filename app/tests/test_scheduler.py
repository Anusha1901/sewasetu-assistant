"""Statutory job repeat/race regressions against disposable development schemas."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import importlib.util
import os
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import services as s
import test_services as support


@unittest.skipUnless(os.environ.get('RUN_DB_TESTS') == '1', 'requires isolated development Postgres')
class SchedulerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support.IntegrationTests.setUpClass.__func__(cls)
        spec = importlib.util.spec_from_file_location('statutory_job_test', Path(s.BASE_DIR) / 'scripts/deemed_approval.py')
        cls.job = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.job)

    @classmethod
    def tearDownClass(cls):
        support.IntegrationTests.tearDownClass.__func__(cls)

    def setUp(self):
        support.IntegrationTests.setUp(self)
        self.notifications = []
        database_patch = patch.object(self.job, 'psycopg2', SimpleNamespace(connect=lambda **kw: s.get_db()))
        sms_patch = patch.object(self.job.requests, 'post', side_effect=lambda *a, **kw: self.notifications.append(kw['json']))
        database_patch.start()
        sms_patch.start()
        self.addCleanup(database_patch.stop)
        self.addCleanup(sms_patch.stop)
        self.app_id = s.submit_application('9900000002', support.data(), '/synthetic-proof.pdf')[0]
        with s.transaction() as cur:
            cur.execute('UPDATE applications SET submitted_at=%s WHERE id=%s',
                        (datetime.now() - timedelta(days=16), self.app_id))

    def counts(self):
        with s.transaction() as cur:
            cur.execute('SELECT status FROM applications WHERE id=%s', (self.app_id,))
            status = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM audit_log WHERE application_id=%s AND action='DEEMED_APPROVED'", (self.app_id,))
            return status, cur.fetchone()[0]

    def test_immediate_repeat_does_not_duplicate_audit_or_notification(self):
        self.job.main()
        self.job.main()
        self.assertEqual(self.counts(), ('DEEMED_APPROVED', 1))
        self.assertEqual(len(self.notifications), 1)

    def test_two_competing_scheduler_runs_have_one_audit_and_notification(self):
        barrier = threading.Barrier(2)
        def run():
            barrier.wait()
            return self.job.main()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: run(), range(2)))
        self.assertEqual(self.counts(), ('DEEMED_APPROVED', 1))
        self.assertEqual(len(self.notifications), 1)

    def test_recent_pending_case_keeps_original_fifteen_day_cutoff(self):
        with s.transaction() as cur:
            cur.execute('UPDATE applications SET submitted_at=%s WHERE id=%s', (datetime.now(), self.app_id))
        self.job.main()
        self.assertEqual(self.counts(), ('PENDING', 0))
        self.assertEqual(self.notifications, [])


if __name__ == '__main__':
    unittest.main()
