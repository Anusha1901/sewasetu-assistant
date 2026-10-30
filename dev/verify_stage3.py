"""Real OAuth browser HTTP + official MCP client; development-only synthetic citizens.

Run via stdin in the development app container. Output contains no tokens or OTPs.
"""
import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import time
from urllib.parse import urlparse, parse_qs

import requests
from fpdf import FPDF
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
import services as s
from citizen_auth import RESOURCE

BASE = 'http://localhost:8000'
checks = []


def check(name, passed):
    checks.append({'check': name, 'passed': bool(passed)})
    print(json.dumps(checks[-1]), flush=True)
    assert passed, name


def query(sql, values=()):
    with s.transaction() as cur:
        cur.execute(sql, values)
        return cur.fetchall()


def mobile():
    while True:
        value = '98' + ''.join(str(secrets.randbelow(10)) for _ in range(8))
        if not query('SELECT 1 FROM applications WHERE mobile=%s', (value,)):
            return value


def login(number, role='citizen', resource=RESOURCE):
    browser = requests.Session()
    client = browser.post(BASE + '/oauth/register', json={'client_name': 'Stage 3 verification', 'redirect_uris': ['http://localhost:9877/callback']}, timeout=20).json()['client_id']
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    r = browser.get(BASE + '/oauth/authorize', params={'client_id': client, 'redirect_uri': 'http://localhost:9877/callback', 'response_type': 'code', 'scope': role, 'resource': resource, 'code_challenge': challenge, 'code_challenge_method': 'S256', 'state': 'stage3-state'}, timeout=20)
    login_url = r.url
    if role == 'citizen':
        browser.post(login_url, data={'mobile': number}, timeout=20)
        code = None
        for _ in range(25):
            msgs = requests.get(BASE + '/__gateway/api/messages', params={'to': number}, timeout=20).json()['messages']
            if msgs and msgs[-1]['delivered']:
                code = re.search(r'\b\d{6}\b', msgs[-1]['text']).group()
                break
            time.sleep(.3)
        assert code
        r = browser.post(login_url, data={'otp': code}, timeout=20)
    else:
        r = browser.post(login_url, data={'username': 'admin', 'password': os.environ['ADMIN_PASSWORD']}, timeout=20)
    check(role + ' browser reaches consent', '/oauth/consent?' in r.url)
    r = browser.post(r.url, data={'decision': 'allow'}, allow_redirects=False, timeout=20)
    values = parse_qs(urlparse(r.headers['Location']).query)
    r = browser.post(BASE + '/oauth/token', data={'grant_type': 'authorization_code', 'client_id': client, 'code': values['code'][0], 'redirect_uri': 'http://localhost:9877/callback', 'code_verifier': verifier, 'resource': resource}, timeout=20)
    check(role + ' token exchange', r.status_code == 200)
    return browser, r.json(), client


def denial(token=None, origin=None):
    headers = {'Accept': 'application/json, text/event-stream'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if origin:
        headers['Origin'] = origin
    return requests.post(RESOURCE, headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'stage3', 'version': '1'}}}, timeout=20)


async def run():
    r = denial()
    check('unauthenticated MCP challenge', r.status_code == 401 and 'resource_metadata=' in r.headers.get('WWW-Authenticate', ''))
    meta = requests.get(BASE + '/.well-known/oauth-protected-resource/mcp/citizen', timeout=20).json()
    check('canonical protected resource discovery', meta['resource'] == RESOURCE and meta['authorization_servers'] == [BASE] and meta['scopes_supported'] == ['citizen'])
    check('invalid bearer rejected', denial('invalid').status_code == 401)
    number = mobile()
    browser, tokens, client = login(number)
    check('untrusted browser origin rejected', denial(tokens['access_token'], 'https://attacker.invalid').status_code == 403)
    _, wrong_role, _ = login(number, role='officer')
    check('officer token denied citizen MCP', denial(wrong_role['access_token']).status_code in (401, 403))
    _, wrong_audience, _ = login(number, resource=BASE + '/wrong-resource')
    check('wrong audience denied', denial(wrong_audience['access_token']).status_code == 401)
    check('officer MCP remains inaccessible without officer authentication', requests.get(BASE + '/mcp/officer', timeout=20).status_code == 401)
    details = {'applicant_name': 'Stage Three Synthetic Applicant', 'dob': '01/01/1950', 'village': 'Synthetic Village', 'block': 'Sonari', 'bank_account': '123456789012', 'ifsc': 'SBIN0003077'}

    async with streamablehttp_client(RESOURCE, headers={'Authorization': 'Bearer ' + tokens['access_token']}) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            check('exactly five citizen tools', {t.name for t in tools.tools} == {'get_scheme_info', 'prepare_application', 'submit_application', 'get_my_applications', 'withdraw_application'})

            async def tool(name, args=None):
                result = await session.call_tool(name, args or {})
                assert not result.isError, name
                if result.structuredContent:
                    return result.structuredContent
                return json.loads(result.content[0].text)

            info = await tool('get_scheme_info')
            check('scheme info uses configured rules', info['agent_supported_blocks'] == ['Sonari', 'Rajapara'] and info['minimum_age'] == 60 and info['deadline_ist'] == '2026-10-31T23:59:00')
            invalid = await tool('prepare_application', {'details': {**details, 'dob': '01/01/2010', 'bank_account': 'abc'}})
            check('invalid application returns errors', not invalid['ready_to_submit'] and len(invalid['errors']) >= 3)
            bad = await tool('prepare_application', {'details': {**details, 'block': 'Namti'}})
            check('unsupported block rejected in preparation', not bad['ready_to_submit'])
            check('unsupported block browser upload denied', browser.get(bad['upload_url'], timeout=20).status_code == 410)
            bad_submit = await tool('submit_application', {'draft_id': bad['draft_id'], 'revision': bad['revision'], 'declaration_accepted': True})
            check('unsupported block rejected on submit', bad_submit['code'] == 'unsupported_block')
            prep = await tool('prepare_application', {'details': details})
            check('no proof prevents readiness', not prep['ready_to_submit'])
            check('upload link alone is not identity', requests.get(prep['upload_url'], timeout=20).status_code == 403)
            token_hash = hashlib.sha256(prep['upload_url'].rsplit('/', 1)[1].encode()).hexdigest()
            # Expire only this synthetic link to verify server-side expiry.
            query('UPDATE citizen_links SET expires_at=0 WHERE token_hash=%s RETURNING token_hash', (token_hash,))
            check('expired upload link rejected', browser.get(prep['upload_url'], timeout=20).status_code == 410)
            prep = await tool('prepare_application', {'draft_id': prep['draft_id']})
            page = browser.get(prep['upload_url'], timeout=20)
            check('matching OAuth browser can open upload', page.status_code == 200)
            csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
            pdf = FPDF(); pdf.add_page(); pdf.set_font('Helvetica', size=12)
            pdf.cell(0, 10, 'SYNTHETIC DEVELOPMENT AGE PROOF')
            content = bytes(pdf.output())
            r = browser.post(prep['upload_url'], data={'csrf': 'incorrect'}, files={'document': ('a.pdf', content, 'application/pdf')}, timeout=20)
            check('upload CSRF rejected', r.status_code == 403)
            r = browser.post(prep['upload_url'], data={'csrf': csrf}, files={'document': ('a.pdf', b'invalid', 'application/pdf')}, timeout=20)
            check('invalid PDF content rejected', r.status_code == 410)
            r = browser.post(prep['upload_url'], data={'csrf': csrf}, files={'document': ('../../proof.pdf', content, 'application/pdf')}, timeout=20)
            check('valid browser upload succeeds', r.status_code == 200 and 'Age proof uploaded' in r.text)
            check('upload link is single use', browser.get(prep['upload_url'], timeout=20).status_code == 410)
            stale = await tool('submit_application', {'draft_id': prep['draft_id'], 'revision': prep['revision'], 'declaration_accepted': True})
            check('stale document preview rejected', stale['code'] == 'stale_preview')
            prep = await tool('prepare_application', {'draft_id': prep['draft_id']})
            check('uploaded proof reflected in current preview', prep['ready_to_submit'] and prep['has_age_proof'])
            no_consent = await tool('submit_application', {'draft_id': prep['draft_id'], 'revision': prep['revision'], 'declaration_accepted': False})
            check('explicit declaration required', no_consent['code'] == 'declaration_required')
            malformed = await session.call_tool('submit_application', {'draft_id': prep['draft_id'], 'revision': prep['revision'], 'declaration_accepted': 'true'})
            check('declaration must be a real boolean', malformed.isError)
            submitted = await tool('submit_application', {'draft_id': prep['draft_id'], 'revision': prep['revision'], 'declaration_accepted': True})
            check('MCP submission persisted', submitted['ok'] and query('SELECT mobile,status FROM applications WHERE id=%s', (submitted['application_id'],)) == [(number, 'PENDING')])
            again = await tool('submit_application', {'draft_id': prep['draft_id'], 'revision': prep['revision'], 'declaration_accepted': True})
            check('duplicate retry returns same application', again['already_submitted'] and again['application_id'] == submitted['application_id'])
            check('one application and one submit audit', query('SELECT count(*) FROM applications WHERE mobile=%s', (number,))[0][0] == 1 and query("SELECT count(*) FROM audit_log WHERE application_id=%s AND action='SUBMIT'", (submitted['application_id'],))[0][0] == 1)
            page = browser.get(submitted['acknowledgment_url'], timeout=20)
            check('browser acknowledgment download', page.status_code == 200 and page.content.startswith(b'%PDF'))
            own = await tool('get_my_applications')
            check('own application history only', len(own['applications']) == 1 and own['applications'][0]['application_id'] == submitted['application_id'])
            denied = await tool('withdraw_application', {'application_id': 1, 'confirmed': True})
            check('other citizen withdrawal denied', denied['code'] == 'not_found')
            confirmation = await tool('withdraw_application', {'application_id': submitted['application_id']})
            check('withdrawal requires confirmation', confirmation['code'] == 'confirmation_required')
            withdrawn = await tool('withdraw_application', {'application_id': submitted['application_id'], 'confirmed': True})
            check('MCP withdrawal persisted with audit', withdrawn['ok'] and query('SELECT status FROM applications WHERE id=%s', (submitted['application_id'],)) == [('WITHDRAWN',)])
            info = await tool('get_scheme_info')

    # Finish immediately invalidates access/refresh and clears browser identity.
    page = browser.get(info['finish_sign_in_url'], timeout=20)
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    check('browser sign-out succeeds', browser.post(info['finish_sign_in_url'], data={'csrf': csrf}, timeout=20).status_code == 200)
    check('signed-out access token immediately rejected', denial(tokens['access_token']).status_code == 401)
    refresh = browser.post(BASE + '/oauth/token', data={'grant_type': 'refresh_token', 'client_id': client, 'refresh_token': tokens['refresh_token'], 'resource': RESOURCE}, timeout=20)
    check('signed-out refresh rejected', refresh.status_code == 400)
    _, expired_tokens, _ = login(number)
    import jwt
    sid = jwt.decode(expired_tokens['access_token'], options={'verify_signature': False})['sid']
    query('UPDATE oauth_agent_sessions SET expires_at=0 WHERE id=%s RETURNING id', (sid,))
    check('expired server session rejected', denial(expired_tokens['access_token']).status_code == 401)
    print(json.dumps({'summary': {'passed': len(checks), 'failed': 0}, 'synthetic_application_id': submitted['application_id']}), flush=True)


asyncio.run(run())
