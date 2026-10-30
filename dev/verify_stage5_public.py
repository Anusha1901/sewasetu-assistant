"""Authorized synthetic public tests through real OAuth and official Streamable HTTP SDK.

Run inside the hosted image with private env supplied by Docker. No secrets are logged.
Only this run's synthetic session expiry rows are edited; applications/decisions use MCP.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, '/app')

import jwt
import httpx
import requests
from fpdf import FPDF
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import documents
import services as s

BASE = os.environ['PUBLIC_BASE_URL'].rstrip('/')
STATE = Path('/evidence')
checks = []
CLIENT_NAME = 'Stage 5 public synthetic verification'
ADMIN_USER = os.environ['ADMIN_USERNAME']
TIMEOUT = 120


def check(name, passed):
    item = {'check': name, 'passed': bool(passed)}
    checks.append(item)
    print(json.dumps(item), flush=True)
    if not passed:
        raise AssertionError(name)


def query(sql, values=()):
    with s.transaction() as cur:
        cur.execute(sql, values)
        return cur.fetchall()


def private_save(name, data):
    STATE.mkdir(mode=0o700, exist_ok=True)
    path = STATE / name
    path.write_text(json.dumps(data, indent=2))
    path.chmod(0o600)


def resource(role):
    return BASE + '/mcp/' + role


def post_denied(token, role):
    return requests.post(resource(role), headers={'Authorization': 'Bearer ' + token,
        'Accept': 'application/json, text/event-stream'},
        json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, timeout=TIMEOUT).status_code


def login(role, admin, mobile=None):
    browser = requests.Session()
    callback = 'http://127.0.0.1:9879/callback'
    response = browser.post(BASE + '/oauth/register', json={'client_name': CLIENT_NAME,
        'redirect_uris': [callback]}, timeout=TIMEOUT)
    response.raise_for_status()
    client = response.json()['client_id']
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(24)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    page = browser.get(BASE + '/oauth/authorize', params={'client_id': client,
        'redirect_uri': callback, 'response_type': 'code', 'scope': role,
        'resource': resource(role), 'code_challenge': challenge,
        'code_challenge_method': 'S256', 'state': state}, timeout=TIMEOUT)
    login_url = page.url
    if role == 'citizen':
        response = browser.post(login_url, data={'mobile': mobile}, timeout=TIMEOUT)
        response.raise_for_status()
        code = None
        for _ in range(30):
            inbox = admin.get(BASE + '/__gateway/api/messages', params={'to': mobile}, timeout=TIMEOUT)
            inbox.raise_for_status()
            messages = inbox.json()['messages']
            if messages and messages[-1]['delivered']:
                match = re.search(r'\b\d{6}\b', messages[-1]['text'] or '')
                if match:
                    code = match[0]
                    break
            time.sleep(.25)
        if code is None:
            raise AssertionError('Synthetic delivered OTP unavailable in protected simulator')
        page = browser.post(login_url, data={'otp': code}, timeout=TIMEOUT)
    else:
        page = browser.post(login_url, data={'username': ADMIN_USER,
            'password': os.environ['ADMIN_PASSWORD']}, timeout=TIMEOUT)
    check(role + ' real browser login reaches consent', '/oauth/consent?' in page.url)
    response = browser.post(page.url, data={'decision': 'allow'}, allow_redirects=False, timeout=TIMEOUT)
    values = parse_qs(urlparse(response.headers['Location']).query)
    check(role + ' OAuth state is returned unchanged', values.get('state') == [state])
    response = browser.post(BASE + '/oauth/token', data={'grant_type': 'authorization_code',
        'client_id': client, 'code': values['code'][0], 'redirect_uri': callback,
        'code_verifier': verifier, 'resource': resource(role)}, timeout=TIMEOUT)
    check(role + ' authorization code plus PKCE exchanges successfully', response.status_code == 200)
    return {'tokens': response.json(), 'client_id': client, 'browser': browser, 'role': role}


@asynccontextmanager
async def connection(identity):
    async with streamablehttp_client(resource(identity['role']),
            headers={'Authorization': 'Bearer ' + identity['tokens']['access_token']},
            timeout=TIMEOUT, sse_read_timeout=TIMEOUT) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            yield client


async def tool(client, name, args=None):
    response = await client.call_tool(name, args or {})
    if response.isError:
        raise AssertionError('Unexpected SDK tool error: ' + name)
    return response.structuredContent or json.loads(response.content[0].text)


def csrf(page):
    return re.search(r'name="csrf" value="([^"]+)"', page.text)[1]


async def submit_case(client, citizen, label):
    details = {'applicant_name': 'Stage Five ' + label + ' Synthetic Applicant',
        'dob': '01/01/1950', 'village': 'Synthetic Test Village', 'block': 'Rajapara',
        'bank_account': '123456789012', 'ifsc': 'SBIN0003077'}
    prep = await tool(client, 'prepare_application', {'details': details})
    check(label + ' missing proof prevents submission readiness', not prep['ready_to_submit'])
    page = citizen['browser'].get(prep['upload_url'], timeout=TIMEOUT)
    check(label + ' authenticated upload page opens', page.status_code == 200)
    pdf = FPDF(); pdf.add_page(); pdf.set_font('Helvetica', size=12)
    pdf.multi_cell(0, 10, 'SYNTHETIC EVALUATION ONLY - NOT A REAL AGE PROOF\n' + details['applicant_name'])
    content = bytes(pdf.output())
    response = citizen['browser'].post(prep['upload_url'], data={'csrf': csrf(page)},
        files={'document': ('synthetic.pdf', content, 'application/pdf')}, timeout=TIMEOUT)
    check(label + ' browser uploads synthetic private PDF', response.status_code == 200 and 'Age proof uploaded' in response.text)
    prep = await tool(client, 'prepare_application', {'draft_id': prep['draft_id']})
    check(label + ' current document preview is ready', prep['ready_to_submit'] and prep['has_age_proof'])
    args = {'draft_id': prep['draft_id'], 'revision': prep['revision'], 'declaration_accepted': True}
    result = await tool(client, 'submit_application', args)
    check(label + ' synthetic case submitted through public MCP', result.get('status') == 'PENDING')
    return result, args


async def proposal(client, app_id, decision, reason):
    case = await tool(client, 'get_application', {'application_id': app_id})
    args = {'application_id': app_id, 'decision': decision, 'reason': reason, 'review_token': case['review_token']}
    preview = await tool(client, 'decide_application', args)
    check('decision preview requires explicit confirmation', preview.get('code') == 'confirmation_required')
    return {**args, 'confirmed': True, 'confirmation_token': preview['confirmation_token']}


def snapshot():
    fixture = json.loads((STATE / 'fixture.json').read_text())
    ids = [100011] + fixture['application_ids']
    result = {'cases': [], 'global': {}}
    with s.transaction() as cur:
        cur.execute('SELECT count(*) FROM applications')
        result['global']['application_count'] = cur.fetchone()[0]
        cur.execute('SELECT count(*) FROM audit_log')
        result['global']['audit_count'] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM audit_log WHERE action='DEEMED_APPROVED'")
        result['global']['deemed_audit_count'] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM applications WHERE status='DEEMED_APPROVED'")
        result['global']['deemed_application_count'] = cur.fetchone()[0]
        cur.execute('SELECT count(*) FROM simulated_sms')
        result['global']['simulated_message_count'] = cur.fetchone()[0]
        cur.execute('SELECT id,application_no,status,decided_by,decided_at,doc_path FROM applications WHERE id IN %s ORDER BY id', (tuple(ids),))
        cases = cur.fetchall()
        for case in cases:
            cur.execute('SELECT action,actor,note,at FROM audit_log WHERE application_id=%s ORDER BY id', (case[0],))
            audit = cur.fetchall()
            result['cases'].append({'id': case[0], 'application_no': case[1], 'status': case[2],
                'decided_by': case[3], 'decided_at': str(case[4]),
                'document_sha256': hashlib.sha256(documents.read(case[5])).hexdigest(),
                'audit_sha256': hashlib.sha256(json.dumps(audit, default=str).encode()).hexdigest(),
                'audit_count': len(audit)})
    return result


async def main():
    check('test target is the approved public evaluation deployment', BASE == 'https://sewasetu-assistant-wgcq.onrender.com')
    admin = requests.Session()
    page = admin.post(BASE + '/admin', data={'username': ADMIN_USER, 'password': os.environ['ADMIN_PASSWORD']}, timeout=TIMEOUT)
    check('simulator access uses authenticated assessor browser', admin.get(BASE + '/__gateway/api/messages', timeout=TIMEOUT).status_code == 200)
    while True:
        mobile = '99' + ''.join(str(secrets.randbelow(10)) for _ in range(8))
        if not query('SELECT 1 FROM applications WHERE mobile=%s', (mobile,)):
            break
    citizen = login('citizen', admin, mobile)
    officer1, officer2 = login('officer', admin), login('officer', admin)
    ids = []
    async with connection(citizen) as c, connection(officer1) as o1, connection(officer2) as o2:
        check('citizen SDK discovers five tools', len((await c.list_tools()).tools) == 5)
        check('officer SDK discovers four tools', len((await o1.list_tools()).tools) == 4)
        check('citizen token cannot access officer MCP', post_denied(citizen['tokens']['access_token'], 'officer') == 401)
        check('officer token cannot access citizen MCP', post_denied(officer1['tokens']['access_token'], 'citizen') == 401)
        case, args = await submit_case(c, citizen, 'Rejection')
        ids.append(case['application_id'])
        viewed = await tool(o1, 'get_application', {'application_id': ids[-1]})
        for decision in ('APPROVED', 'REJECTED'):
            denied = await tool(o1, 'decide_application', {'application_id': ids[-1], 'decision': decision,
                'reason': '  ', 'review_token': viewed['review_token']})
            check(decision + ' requires nonblank reason on public server', denied.get('code') == 'invalid_decision')
        reason = 'Synthetic rejection test: the uploaded document is explicitly fictional and does not establish age.'
        decision = await proposal(o1, ids[-1], 'REJECTED', reason)
        check('rejection preview leaves application pending', query('SELECT status FROM applications WHERE id=%s', (ids[-1],)) == [('PENDING',)])
        rejected = await tool(o1, 'decide_application', decision)
        check('public rejection succeeds after explicit test confirmation', rejected.get('status') == 'REJECTED')
        check('rejection audit records exact reason and authenticated actor',
              query("SELECT actor,note FROM audit_log WHERE application_id=%s AND action='REJECTED'", (ids[-1],)) == [('admin:' + ADMIN_USER, reason)])
        repeat = await tool(c, 'submit_application', args)
        check('submission retry remains idempotent after rejection', repeat.get('already_submitted') and repeat['application_id'] == ids[-1])
        history = await tool(c, 'get_my_applications')
        check('citizen sees rejected status and exact reason', history['applications'][0]['status'] == 'REJECTED' and history['applications'][0]['decision_reason'] == reason)
        case, _ = await submit_case(c, citizen, 'Withdrawal')
        ids.append(case['application_id'])
        denied = await tool(c, 'withdraw_application', {'application_id': ids[-1], 'confirmed': False})
        check('public withdrawal requires explicit confirmation', denied.get('code') == 'confirmation_required')
        withdrawn = await tool(c, 'withdraw_application', {'application_id': ids[-1], 'confirmed': True})
        check('public citizen withdrawal succeeds', withdrawn.get('status') == 'WITHDRAWN')
        check('withdrawal audit uses authenticated citizen', query("SELECT actor FROM audit_log WHERE application_id=%s AND action='WITHDRAW'", (ids[-1],)) == [('applicant:' + mobile,)])
        check('withdrawn case cannot be withdrawn again', (await tool(c, 'withdraw_application', {'application_id': ids[-1], 'confirmed': True})).get('code') == 'not_pending')
        case, _ = await submit_case(c, citizen, 'Competing Decisions')
        ids.append(case['application_id'])
        a = await proposal(o1, ids[-1], 'APPROVED', 'Synthetic concurrency test approval; no real entitlement or payment.')
        b = await proposal(o2, ids[-1], 'REJECTED', 'Synthetic concurrency test rejection; fictional proof.')
        check('competing previews do not record a decision', query('SELECT status FROM applications WHERE id=%s', (ids[-1],)) == [('PENDING',)])
        results = await asyncio.gather(tool(o1, 'decide_application', a), tool(o2, 'decide_application', b))
        check('two independent officer clients have exactly one winner', sum(bool(r.get('ok')) for r in results) == 1)
        winner = next(r for r in results if r.get('ok'))
        check('competing decisions produce exactly one decision audit',
              query("SELECT action,actor,note FROM audit_log WHERE application_id=%s AND action IN ('APPROVED','REJECTED')", (ids[-1],)) == [(winner['status'], 'admin:' + ADMIN_USER, winner['reason'])])
        check('race outcome is stored without overwrite', query('SELECT status FROM applications WHERE id=%s', (ids[-1],)) == [(winner['status'],)])
        check('synthetic identity cannot withdraw another citizen case',
              (await tool(c, 'withdraw_application', {'application_id': 100011, 'confirmed': True})).get('code') == 'not_found')
        check('unsupported officer block remains denied', (await tool(o1, 'list_applications', {'block': 'Namti'})).get('code') == 'unsupported_block')
    # Expire only separately authenticated test sessions. Keep the user's Codex sessions untouched.
    for role in ('citizen', 'officer'):
        identity = login(role, admin, mobile if role == 'citizen' else None)
        check(role + ' token initially reaches protected tools', post_denied(identity['tokens']['access_token'], role) != 401)
        claims = jwt.decode(identity['tokens']['access_token'], options={'verify_signature': False})
        changed = query('UPDATE oauth_agent_sessions SET expires_at=%s WHERE id=%s AND client_id=%s RETURNING id',
                        (int(time.time()) - 1, claims['sid'], identity['client_id']))
        check(role + ' expiry fixture affects only its dedicated session', len(changed) == 1)
        check(role + ' expired server session rejects protected tools', post_denied(identity['tokens']['access_token'], role) == 401)
        refreshed = requests.post(BASE + '/oauth/token', data={'grant_type': 'refresh_token', 'client_id': identity['client_id'],
            'refresh_token': identity['tokens']['refresh_token'], 'resource': resource(role)}, timeout=TIMEOUT)
        check(role + ' expired session cannot refresh', refreshed.status_code == 400)
        identity = login(role, admin, mobile if role == 'citizen' else None)
        response = requests.post(BASE + '/oauth/revoke', data={'token': identity['tokens']['refresh_token']}, timeout=TIMEOUT)
        check(role + ' standard OAuth revocation endpoint succeeds', response.status_code == 200)
        check(role + ' revoked access cannot reach protected tools', post_denied(identity['tokens']['access_token'], role) == 401)
        refreshed = requests.post(BASE + '/oauth/token', data={'grant_type': 'refresh_token', 'client_id': identity['client_id'],
            'refresh_token': identity['tokens']['refresh_token'], 'resource': resource(role)}, timeout=TIMEOUT)
        check(role + ' revoked refresh token cannot mint new access', refreshed.status_code == 400)
    # Fresh officer session for the quiet-window reconnect and restart checks; tokens stay ignored/private.
    identity = login('officer', admin)
    private_save('officer-session.json', {k: v for k, v in identity.items() if k != 'browser'})
    private_save('fixture.json', {'application_ids': ids, 'created_at_utc': datetime.now(timezone.utc).isoformat()})
    private_save('before-restart.json', snapshot())
    print(json.dumps({'summary': {'passed': len(checks), 'failed': 0}, 'synthetic_application_ids': ids,
                      'quiet_window_can_start_utc': datetime.now(timezone.utc).isoformat()}), flush=True)


async def reconnect():
    identity = json.loads((STATE / 'officer-session.json').read_text())
    started = time.monotonic()
    async with connection(identity) as client:
        check('fresh external SDK connection discovers officer tools', len((await client.list_tools()).tools) == 4)
        summary = await tool(client, 'get_queue_summary')
        check('reconnected client calls protected officer tool', summary.get('ok') and summary.get('officer') == ADMIN_USER)
    print(json.dumps({'reconnect_seconds': round(time.monotonic() - started, 3)}), flush=True)


async def cold():
    quiet = json.loads((STATE / 'quiet-window.json').read_text())
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(quiet['started_at_utc'])).total_seconds()
    check('cold reconnect waits at least sixteen minutes without test traffic', elapsed >= 960)
    identity = json.loads((STATE / 'officer-session.json').read_text())
    started = time.monotonic()
    first_response = None

    async def observe(response):
        nonlocal first_response
        if first_response is None:
            first_response = {'status': response.status_code,
                'content_type': response.headers.get('content-type'),
                'seconds_to_headers': round(time.monotonic() - started, 3)}

    def factory(**kwargs):
        kwargs.setdefault('follow_redirects', True)
        kwargs['event_hooks'] = {'response': [observe]}
        return httpx.AsyncClient(**kwargs)

    async def attempt():
        async with streamablehttp_client(resource('officer'),
                headers={'Authorization': 'Bearer ' + identity['tokens']['access_token']},
                timeout=120, sse_read_timeout=120, httpx_client_factory=factory) as (read, write, _):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = await client.list_tools()
                summary = await tool(client, 'get_queue_summary')
                return len(tools.tools) == 4 and summary.get('ok') and summary.get('officer') == ADMIN_USER

    first_ok = False
    try:
        first_ok = bool(await attempt())
    except Exception as error:
        print(json.dumps({'cold_first_attempt_error_type': type(error).__name__,
                          'private_exception_details_withheld': True}), flush=True)
    print(json.dumps({'quiet_seconds': round(elapsed, 3), 'first_response': first_response,
                      'first_attempt_succeeded': first_ok}), flush=True)
    if not first_ok:
        await asyncio.sleep(2)
        check('external MCP client reconnects after cold-start retry', await attempt())
    else:
        check('external MCP client connects on first post-idle attempt', True)
    print(json.dumps({'cold_reconnect_total_seconds': round(time.monotonic() - started, 3)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['full', 'snapshot', 'compare', 'reconnect', 'cold'])
    args = parser.parse_args()
    try:
        if args.mode == 'full':
            asyncio.run(main())
        elif args.mode == 'snapshot':
            private_save('before-restart.json', snapshot())
            print('Saved private persistence baseline; no credentials printed.')
        elif args.mode == 'compare':
            before = json.loads((STATE / 'before-restart.json').read_text())
            after = snapshot()
            check('application records and exact private documents persist', before['cases'] == after['cases'])
            for key in before['global']:
                check('persistent global ' + key + ' unchanged', before['global'][key] == after['global'][key])
        elif args.mode == 'reconnect':
            asyncio.run(reconnect())
        else:
            asyncio.run(cold())
    except BaseException as exc:
        print(json.dumps({'failure_type': type(exc).__name__, 'details': 'Private exception details withheld; inspect failed check.'}), flush=True)
        raise SystemExit(1)
