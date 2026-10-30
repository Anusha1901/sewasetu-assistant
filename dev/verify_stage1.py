"""Run inside the isolated app container via stdin. Uses real HTTP and read-only SQL.

Synthetic test applicants and OAuth clients are retained in development volumes.
No direct INSERT/UPDATE, mocked authentication, or eligibility/deadline changes.
"""
import base64
import hashlib
import io
import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
import jwt
from fpdf import FPDF
import app as portal

BASE = 'http://localhost:8000'
checks = []


def check(name, condition):
    checks.append({'check': name, 'passed': bool(condition)})
    print(json.dumps(checks[-1]), flush=True)
    if not condition:
        raise AssertionError(name)


def call(s, method, path, **kw):
    return s.request(method, BASE + path, timeout=20, **kw)


def sql(query, params=()):
    with portal.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def otp(mobile):
    for _ in range(20):
        msgs = requests.get(BASE + '/__gateway/api/messages', params={'to': mobile}, timeout=10).json()['messages']
        if msgs and msgs[-1]['delivered'] and 'OTP' in (msgs[-1]['text'] or ''):
            return re.search(r'\b\d{6}\b', msgs[-1]['text']).group()
        time.sleep(.5)
    raise AssertionError('SMS delivery timeout')


def new_citizen():
    while True:
        mobile = '99' + ''.join(str(secrets.randbelow(10)) for _ in range(8))
        if not sql('SELECT id FROM applications WHERE mobile=%s', (mobile,)):
            break
    s = requests.Session()
    r = call(s, 'GET', '/apply')
    match = re.search(r'What is (\d+) \+ (\d+)', r.text)
    check('captcha form loads', bool(match))
    answer = sum(map(int, match.groups()))
    r = call(s, 'POST', '/apply', data={'mobile': mobile, 'captcha': answer})
    check('OTP sent through portal', r.status_code == 200 and '/verify' in r.url)
    r = call(s, 'POST', '/verify', data={'otp': 'invalid'})
    check('invalid OTP rejected', 'Invalid OTP' in r.text)
    r = call(s, 'POST', '/verify', data={'otp': otp(mobile)})
    check('delivered OTP accepted', r.url.endswith('/form/1'))
    return s, mobile


def form(s, dob='01/01/1950', block='Sonari', bank='123456789012'):
    call(s, 'POST', '/form/1', data={'applicant_name': 'Stage One Synthetic Applicant', 'dob': dob, 'gender': 'Female', 'marital_status': 'Widowed'})
    call(s, 'POST', '/form/2', data={'village': 'Stage One Test Village', 'block': block})
    call(s, 'POST', '/form/3', data={'bank_account': bank, 'ifsc': 'SBIN0003077'})


def upload(s):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', size=12)
    pdf.cell(0, 10, 'SYNTHETIC DEVELOPMENT AGE PROOF - NOT A REAL DOCUMENT')
    r = call(s, 'POST', '/upload', files={'document': ('stage1-proof.pdf', bytes(pdf.output()), 'application/pdf')})
    check('PDF upload and declaration preview', r.status_code == 200 and r.url.endswith('/declaration'))


def submit(s, mobile):
    r = call(s, 'POST', '/declaration', data={'declaration': 'accepted'})
    rows = sql('SELECT id, application_no, status, doc_path FROM applications WHERE mobile=%s ORDER BY id DESC', (mobile,))
    check('submission persisted and confirmation rendered', len(rows) == 1 and rows[0][2] == 'PENDING' and rows[0][1] in r.text)
    check('uploaded document exists', Path(rows[0][3]).is_file())
    check('submit audit exists', sql("SELECT action FROM audit_log WHERE application_id=%s", (rows[0][0],)) == [('SUBMIT',)])
    return rows[0][0]


def oauth_flow(role, mobile=None):
    s = requests.Session()
    redirect = 'http://localhost:9876/callback'
    r = call(s, 'POST', '/oauth/register', json={'client_name': 'Stage 1 local verification', 'redirect_uris': [redirect], 'token_endpoint_auth_method': 'none'})
    check(role + ' OAuth client registration', r.status_code == 201)
    client = r.json()['client_id']
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    resource = BASE + '/stage1-' + role
    state = secrets.token_urlsafe(16)
    r = call(s, 'GET', '/oauth/authorize', params={'client_id': client, 'redirect_uri': redirect, 'scope': role, 'response_type': 'code', 'code_challenge': challenge, 'code_challenge_method': 'S256', 'resource': resource, 'state': state})
    login_path = r.url.removeprefix(BASE)
    check(role + ' OAuth login page', r.status_code == 200 and '/oauth/login?' in r.url)
    if role == 'citizen':
        call(s, 'POST', login_path, data={'mobile': mobile})
        time.sleep(1)
        r = call(s, 'POST', login_path, data={'otp': otp(mobile)})
    else:
        r = call(s, 'POST', login_path, data={'username': 'admin', 'password': os.environ['ADMIN_PASSWORD']})
    check(role + ' OAuth consent reached', '/oauth/consent?' in r.url)
    r = call(s, 'POST', r.url.removeprefix(BASE), data={'decision': 'allow'}, allow_redirects=False)
    q = parse_qs(urlparse(r.headers['Location']).query)
    check(role + ' OAuth state returned', q['state'] == [state])
    data = {'grant_type': 'authorization_code', 'client_id': client, 'code': q['code'][0], 'code_verifier': verifier, 'redirect_uri': redirect, 'resource': resource}
    r = call(s, 'POST', '/oauth/token', data=data)
    check(role + ' OAuth token exchange', r.status_code == 200)
    tokens = r.json()
    key = jwt.PyJWK.from_dict(requests.get(BASE + '/.well-known/jwks.json', timeout=10).json()['keys'][0]).key
    claims = jwt.decode(tokens['access_token'], key, algorithms=['RS256'], audience=resource, issuer=BASE)
    check(role + ' JWT signature, issuer, audience, role, subject', claims['role'] == role and claims['scope'] == role and claims['sub'] == (('citizen:' + mobile) if role == 'citizen' else 'officer:admin'))
    check(role + ' access lifetime bounded', 0 < claims['exp'] - claims['iat'] <= (1200 if role == 'citizen' else 1800))
    check(role + ' authorization code single use', call(s, 'POST', '/oauth/token', data=data).status_code == 400)
    refresh_data = {'grant_type': 'refresh_token', 'client_id': client, 'refresh_token': tokens['refresh_token'], 'resource': resource}
    refreshed = call(s, 'POST', '/oauth/token', data=refresh_data)
    check(role + ' refresh rotation and fixed session end', refreshed.status_code == 200 and refreshed.json()['session_ends'] == tokens['session_ends'] and refreshed.json()['refresh_token'] != tokens['refresh_token'])
    check(role + ' old refresh rejected', call(s, 'POST', '/oauth/token', data=refresh_data).status_code == 400)
    refresh_data['refresh_token'] = refreshed.json()['refresh_token']
    check(role + ' revoke endpoint', call(s, 'POST', '/oauth/revoke', data={'token': refresh_data['refresh_token']}).status_code == 200)
    check(role + ' revoked refresh rejected', call(s, 'POST', '/oauth/token', data=refresh_data).status_code == 400)


check('Postgres SELECT 1', sql('SELECT 1') == [(1,)])
print(json.dumps({'baseline_statuses': dict(sql('SELECT status,count(*) FROM applications GROUP BY status')), 'application_count': sql('SELECT count(*) FROM applications')[0][0], 'audit_count': sql('SELECT count(*) FROM audit_log')[0][0]}))
for path in ['/', '/about', '/apply', '/status', '/admin', '/__gateway/']:
    check('GET ' + path, requests.get(BASE + path, timeout=20).status_code == 200)
metadata = requests.get(BASE + '/.well-known/oauth-authorization-server', timeout=20).json()
check('OAuth discovery', metadata['issuer'] == BASE and set(metadata['scopes_supported']) == {'citizen', 'officer'})
check('JWKS available', len(requests.get(BASE + '/.well-known/jwks.json', timeout=20).json()['keys']) == 1)
admin = requests.Session()
r = call(admin, 'GET', '/admin/dashboard', allow_redirects=False)
check('anonymous officer dashboard denied', r.status_code == 302 and r.headers['Location'].endswith('/admin'))
check('wrong officer password rejected', 'Invalid credentials' in call(admin, 'POST', '/admin', data={'username': 'admin', 'password': 'incorrect'}).text)
r = call(admin, 'POST', '/admin', data={'username': 'admin', 'password': os.environ['ADMIN_PASSWORD']})
check('officer dashboard login', r.status_code == 200 and r.url.endswith('/admin/dashboard'))

s, mobile = new_citizen()
form(s)
check('missing proof rejected in preview', 'age proof document is required' in call(s, 'GET', '/declaration').text)
upload(s)
for label, args, error in [('underage', {'dob': '01/01/2010'}, '60 years'), ('invalid block', {'block': 'Invalid'}, 'block must be'), ('invalid bank', {'bank': 'abc'}, '9 to 18 digits')]:
    form(s, **args)
    r = call(s, 'POST', '/declaration')
    check(label + ' submission rejected', error in r.text and not sql('SELECT id FROM applications WHERE mobile=%s', (mobile,)))
form(s)
app_id = submit(s, mobile)
check('own application readable', call(s, 'GET', f'/application/{app_id}').status_code == 200)
pdf = call(s, 'GET', f'/ack/{app_id}.pdf')
check('acknowledgment PDF', pdf.status_code == 200 and pdf.content.startswith(b'%PDF'))
other = requests.Session()
call(other, 'POST', '/status', data={'mobile': mobile, 'password': '01011950'})
check('DOB status login', call(other, 'GET', f'/application/{app_id}').status_code == 200)
check('other citizen record denied', call(other, 'GET', '/application/1').status_code == 404)
check('other citizen acknowledgment denied', call(other, 'GET', '/ack/1.pdf').status_code == 403)
for path in ['/admin/applications', '/admin/applications?mobile=' + mobile, f'/admin/application/{app_id}']:
    check('officer ' + path.split('?')[0], call(admin, 'GET', path).status_code == 200)
call(admin, 'POST', f'/admin/approve/{app_id}', data={'note': 'Stage 1 synthetic approval'})
check('officer approval persisted', sql('SELECT status,decided_by FROM applications WHERE id=%s', (app_id,)) == [('APPROVED', 'admin')])
check('approval reason and actor audited', sql("SELECT actor,note FROM audit_log WHERE application_id=%s AND action='APPROVED'", (app_id,)) == [('admin:admin', 'Stage 1 synthetic approval')])

s2, mobile2 = new_citizen()
form(s2); upload(s2)
id2 = submit(s2, mobile2)
call(s2, 'POST', f'/application/{id2}/withdraw')
check('pending withdrawal persisted and audited', sql('SELECT status FROM applications WHERE id=%s', (id2,)) == [('WITHDRAWN',)] and bool(sql("SELECT id FROM audit_log WHERE application_id=%s AND action='WITHDRAW'", (id2,))))

s3, mobile3 = new_citizen()
form(s3); upload(s3)
id3 = submit(s3, mobile3)
call(admin, 'POST', f'/admin/reject/{id3}', data={'note': 'Stage 1 synthetic rejection'})
check('officer rejection persisted and audited', sql('SELECT status,decided_by FROM applications WHERE id=%s', (id3,)) == [('REJECTED', 'admin')] and sql("SELECT actor,note FROM audit_log WHERE application_id=%s AND action='REJECTED'", (id3,)) == [('admin:admin', 'Stage 1 synthetic rejection')])
oauth_flow('citizen', mobile3)
oauth_flow('officer')
print(json.dumps({'summary': {'passed': len(checks), 'failed': 0}, 'test_application_ids': [app_id, id2, id3], 'final_statuses': dict(sql('SELECT status,count(*) FROM applications GROUP BY status'))}), flush=True)
