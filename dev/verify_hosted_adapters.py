"""Local Render-image rehearsal against a disposable database, never Supabase."""
import importlib
import json
import os
from pathlib import Path
import sys
import uuid

import psycopg2
from psycopg2 import sql
from werkzeug.test import Client
from werkzeug.wrappers import Response
import services

sys.path.insert(0, '/app/hosting')
import initialize_hosted
import simulator.app as sms

checks = []


def check(name, condition):
    assert condition, name
    checks.append(name)
    print(json.dumps({'check': name, 'passed': True}), flush=True)


name = 'stage5_hosted_' + uuid.uuid4().hex
original_options = os.environ.get('PGOPTIONS')
original_name = services.config.get('database', 'name')
admin = services.get_db()
admin.autocommit = True
created = False
try:
    with admin.cursor() as cur:
        cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        created = True
    services.config['database']['name'] = name
    os.environ['PGOPTIONS'] = '-c search_path=sewasetu'
    initialize_hosted.initialize()
    with services.transaction() as cur:
        cur.execute('SELECT count(*) FROM applications')
        check('original 100000-row seed imports into empty private schema', cur.fetchone()[0] == 100000)
        cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        check('portal tables stay outside public schema', cur.fetchone()[0] == 0)
        cur.execute("SELECT NOT EXISTS (SELECT 1 FROM pg_namespace n, "
                    "LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) a "
                    "WHERE n.nspname='sewasetu' AND a.grantee=0)")
        check('PUBLIC has no private-schema privileges', cur.fetchone()[0])
    try:
        initialize_hosted.initialize()
    except RuntimeError:
        check('repeated seed import refuses to overwrite records', True)
    else:
        raise AssertionError('Repeated seed import succeeded')
    os.environ['PERSISTENT_SMS'] = '1'
    client = Client(sms.app, Response)
    sent = client.post('/api/send', json={'to': '9900000000', 'text': 'Synthetic hosted simulator test'})
    check('persistent simulator accepts synthetic notification', sent.status_code == 200)
    stored_id = sent.json['id']
    importlib.reload(sms)
    client = Client(sms.app, Response)
    messages = client.get('/api/messages?to=9900000000').json['messages']
    check('simulator process reload preserves queued notification', messages[0]['id'] == stored_id)
    check('simulator recipient filter excludes other recipients', client.get('/api/messages?to=9900000001').json['messages'] == [])
    check('simulator never returns an undelivered OTP as plaintext', messages[0]['text'] is None)
    with services.transaction() as cur:
        cur.execute('UPDATE simulated_sms SET delivery_at=0 WHERE id=%s', (stored_id,))
    check('delivered notification remains readable after restart',
          client.get('/api/messages?to=9900000000').json['messages'][0]['text'] == 'Synthetic hosted simulator test')
    with services.transaction() as cur:
        cur.execute('SELECT count(*) FROM applications')
        check('simulator tests preserve all seeded applications', cur.fetchone()[0] == 100000)
    print(json.dumps({'summary': {'passed': len(checks), 'failed': 0}}), flush=True)
finally:
    services.config['database']['name'] = original_name
    if original_options is None:
        os.environ.pop('PGOPTIONS', None)
    else:
        os.environ['PGOPTIONS'] = original_options
    if created:
        with admin.cursor() as cur:
            # Only the unique database created by this invocation is removed.
            cur.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
    admin.close()
