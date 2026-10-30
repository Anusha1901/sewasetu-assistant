"""Post-restart HTTP and read-only SQL checks for the isolated Stage 1 database."""
import json
import os
import re
import time
from pathlib import Path
import requests
import app as portal

base = 'http://localhost:8000'
expected_applications = int(os.environ.get('STAGE1_EXPECTED_APPLICATIONS', '6'))
expected_clients = int(os.environ.get('STAGE1_EXPECTED_CLIENTS', '3'))
expected_deemed = int(os.environ.get('STAGE1_EXPECTED_DEEMED', '9700'))


def check(name, condition):
    print(json.dumps({'check': name, 'passed': bool(condition)}), flush=True)
    assert condition, name


with portal.get_db() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT id,mobile,status,doc_path FROM applications WHERE applicant_name='Stage One Synthetic Applicant' ORDER BY id")
        rows = cur.fetchall()
        check('synthetic applications persisted across restart', len(rows) == expected_applications)
        check('uploaded proof files persisted across restart', all(Path(r[3]).is_file() for r in rows))
        cur.execute('SELECT count(*) FROM audit_log WHERE application_id IN %s', (tuple(r[0] for r in rows),))
        check('synthetic audit entries persisted', cur.fetchone()[0] == 2 * expected_applications)
        cur.execute("SELECT count(*) FROM applications WHERE status='DEEMED_APPROVED'")
        check('scheduler updates persisted without additional changes', cur.fetchone()[0] == expected_deemed)
        cur.execute("SELECT count(*) FROM audit_log WHERE action='DEEMED_APPROVED'")
        check('scheduler audit did not duplicate on delayed restart', cur.fetchone()[0] == expected_deemed)
        cur.execute('SELECT count(*) FROM oauth_clients')
        check('OAuth clients persisted', cur.fetchone()[0] == expected_clients)

for path in ['/', '/admin', '/__gateway/', '/.well-known/oauth-authorization-server', '/.well-known/jwks.json']:
    check('post-restart GET ' + path, requests.get(base + path, timeout=20).status_code == 200)

app_id, mobile, status, doc_path = next(r for r in rows if r[2] == 'APPROVED')
s = requests.Session()
r = s.get(base + '/apply', timeout=20)
a, b = re.search(r'What is (\d+) \+ (\d+)', r.text).groups()
s.post(base + '/apply', data={'mobile': mobile, 'captcha': int(a) + int(b)}, timeout=20)
code = None
for _ in range(20):
    msgs = s.get(base + '/__gateway/api/messages', params={'to': mobile}, timeout=20).json()['messages']
    if msgs and msgs[-1]['delivered']:
        code = re.search(r'\b\d{6}\b', msgs[-1]['text']).group()
        break
    time.sleep(.5)
check('SMS gateway accepts fresh OTP after restart', bool(code))
s.post(base + '/verify', data={'otp': code}, timeout=20)
s.post(base + '/form/1', data={'applicant_name': 'Stage One Synthetic Applicant', 'dob': '01/01/1950'}, timeout=20)
s.post(base + '/form/2', data={'village': 'Stage One Test Village', 'block': 'Sonari'}, timeout=20)
s.post(base + '/form/3', data={'bank_account': '123456789012', 'ifsc': 'SBIN0003077'}, timeout=20)
with open(doc_path, 'rb') as f:
    s.post(base + '/upload', files={'document': ('duplicate-proof.pdf', f, 'application/pdf')}, timeout=20)
r = s.post(base + '/declaration', data={'declaration': 'accepted'}, timeout=20)
check('duplicate active application rejected', 'already exists for this mobile number' in r.text)
with portal.get_db() as conn:
    with conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM applications WHERE mobile=%s', (mobile,))
        check('duplicate attempt inserted no application', cur.fetchone()[0] == 1)
        cur.execute("SELECT count(*) FROM applications WHERE applicant_name='Stage One Synthetic Applicant'")
        check('final synthetic record count unchanged', cur.fetchone()[0] == expected_applications)
print(json.dumps({'summary': 'persistence and duplicate checks passed'}))
