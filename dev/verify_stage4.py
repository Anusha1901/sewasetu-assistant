"""Official SDK officer OAuth and live MCP tests; only synthetic development cases."""
import asyncio
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
import jwt
from fpdf import FPDF
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientMetadata
import app as portal
import services as s
from officer_auth import RESOURCE
from oauth import mint_access_token

BASE = 'http://localhost:8000'
checks = []
fixtures = []


def check(name, passed):
    checks.append({'check': name, 'passed': bool(passed)})
    print(json.dumps(checks[-1]), flush=True)
    assert passed, name


def query(sql, args=()):
    with s.transaction() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def fixture(block):
    while True:
        mobile = '96' + ''.join(str(secrets.randbelow(10)) for _ in range(8))
        if not query('SELECT 1 FROM applications WHERE mobile=%s', (mobile,)):
            break
    pdf = FPDF(); pdf.add_page(); pdf.set_font('Helvetica', size=12)
    pdf.cell(0, 10, 'SYNTHETIC STAGE FOUR PROOF - NOT A REAL DOCUMENT')
    path = Path(s.config.get('app', 'upload_dir')) / 'agent' / ('stage4-' + secrets.token_hex(16) + '.pdf')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(pdf.output()))
    data = dict(applicant_name='Stage Four Synthetic Applicant', dob='01/01/1950', village='Synthetic Village',
                block=block, bank_account='123456789012', ifsc='SBIN0003077')
    app_id, number = s.submit_application(mobile, data, str(path))
    fixtures.append((app_id, mobile))
    return app_id, number, mobile


class Storage:
    tokens = None
    client = None

    async def get_tokens(self): return self.tokens
    async def set_tokens(self, v): self.tokens = v
    async def get_client_info(self): return self.client
    async def set_client_info(self, v): self.client = v


def make_auth():
    browser = requests.Session()
    storage = Storage()
    callback = None
    async def redirect(url):
        nonlocal callback
        page = browser.get(url, timeout=20)
        page = browser.post(page.url, data={'username': 'admin', 'password': os.environ['ADMIN_PASSWORD']}, timeout=20)
        assert '/oauth/consent?' in page.url
        response = browser.post(page.url, data={'decision': 'allow'}, allow_redirects=False, timeout=20)
        args = parse_qs(urlparse(response.headers['Location']).query)
        callback = args['code'][0], args['state'][0]
    async def receive(): return callback
    auth = OAuthClientProvider(server_url=RESOURCE,
        client_metadata=OAuthClientMetadata(client_name='Stage 4 official officer client',
            redirect_uris=['http://localhost:9879/callback'], grant_types=['authorization_code', 'refresh_token'],
            response_types=['code'], token_endpoint_auth_method='none', scope='officer'),
        storage=storage, redirect_handler=redirect, callback_handler=receive)
    return auth, storage, browser


def request(token=None, endpoint=RESOURCE, origin=None):
    headers = {'Accept': 'application/json, text/event-stream'}
    if token: headers['Authorization'] = 'Bearer ' + token
    if origin: headers['Origin'] = origin
    return requests.post(endpoint, headers=headers, json={'jsonrpc':'2.0','id':1,'method':'tools/list'}, timeout=20)


async def tool(client, name, args=None):
    result = await client.call_tool(name, args or {})
    assert not result.isError, name
    return result.structuredContent or json.loads(result.content[0].text)


async def main():
    response = request()
    check('officer MCP unauthenticated challenge', response.status_code == 401 and '/mcp/officer' in response.headers.get('WWW-Authenticate', ''))
    metadata = requests.get(BASE + '/.well-known/oauth-protected-resource/mcp/officer', timeout=20).json()
    check('separate officer resource metadata', metadata['resource'] == RESOURCE and metadata['scopes_supported'] == ['officer'] and metadata['authorization_servers'] == [BASE])
    check('invalid officer bearer rejected', request('invalid').status_code == 401)
    a, _, am = fixture('Sonari')
    b, _, bm = fixture('Rajapara')
    hidden, _, hm = fixture('Namti')
    competing, _, cm = fixture('Sonari')
    withdrawn, _, wm = fixture('Sonari')
    deemed, _, dm = fixture('Sonari')
    auth, storage, browser = make_auth()
    async with streamablehttp_client(RESOURCE, auth=auth) as (read, write, _):
        async with ClientSession(read, write) as client:
            await client.initialize()
            tools = await client.list_tools()
            check('exactly four officer tools via automatic OAuth discovery/DCR/PKCE', {t.name for t in tools.tools} == {'get_queue_summary','list_applications','get_application','decide_application'})
            claims = jwt.decode(storage.tokens.access_token, options={'verify_signature': False})
            check('officer token role subject scope and lifetimes', claims['role'] == 'officer' and claims['scope'] == 'officer' and claims['sub'] == 'officer:admin' and claims['exp']-claims['iat'] <= 1800 and claims['session_ends']-claims['iat'] <= 28800)
            check('officer token cannot access citizen server', request(storage.tokens.access_token, BASE+'/mcp/citizen').status_code == 401)
            check('invalid officer browser origin denied', request(storage.tokens.access_token, origin='https://attacker.invalid').status_code == 403)
            for role, scope, audience, label in [('citizen','officer',RESOURCE,'citizen role'), ('officer','citizen',RESOURCE,'citizen scope'), ('officer','officer',BASE+'/mcp/citizen','wrong audience')]:
                bad, _ = mint_access_token('officer:admin', role, scope, audience, claims['client_id'],
                    session_ends=datetime.now()+timedelta(hours=8), agent_session_id=claims['sid'])
                check(label+' denied officer MCP', request(bad).status_code == 401)
            expired, _ = mint_access_token('officer:admin', 'officer','officer',RESOURCE,claims['client_id'],ttl=-1,
                session_ends=datetime.now()+timedelta(hours=8), agent_session_id=claims['sid'])
            check('expired JWT rejected', request(expired).status_code == 401)
            summary = await tool(client, 'get_queue_summary')
            check('queue summary excludes unsupported blocks', set(summary['pending_by_block']) == {'Sonari','Rajapara'} and summary['counts_by_status']['PENDING'] == 5)
            listed = await tool(client, 'list_applications', {'mobile': am})
            check('mobile search returns only permitted matching case', [r['application_id'] for r in listed['applications']] == [a])
            check('queue response minimizes citizen PII', 'mobile' not in listed['applications'][0] and 'bank_account' not in listed['applications'][0])
            denied = await tool(client, 'list_applications', {'block':'Namti'})
            check('unsupported block filter denied', denied['code'] == 'unsupported_block')
            denied = await tool(client, 'get_application', {'application_id':hidden})
            check('unsupported case inspection denied', denied['code'] == 'not_found')
            view = await tool(client, 'get_application', {'application_id':a})
            check('case inspection contains audit and masked details', view['age_proof_available'] and view['bank_account_last4']=='9012' and 'bank_account' not in view and 'doc_path' not in view and len(view['audit']) == 1)
            check('proof capability alone does not grant access', requests.get(view['age_proof_url'], timeout=20).status_code == 403)
            proof = browser.get(view['age_proof_url'], timeout=20)
            check('authenticated officer browser downloads proof', proof.status_code==200 and proof.content.startswith(b'%PDF') and 'attachment' in proof.headers['Content-Disposition'])
            token_hash=hashlib.sha256(view['age_proof_url'].rsplit('/',1)[1].encode()).hexdigest()
            query('UPDATE officer_links SET expires_at=0 WHERE token_hash=%s RETURNING token_hash',(token_hash,))
            check('expired officer proof link denied', browser.get(view['age_proof_url'],timeout=20).status_code==410)
            args={'application_id':a,'decision':'APPROVED','reason':'Age and evidence verified at Stage 4 test','review_token':view['review_token']}
            blank=await client.call_tool('decide_application',{**args,'reason':''})
            check('blank reason rejected', blank.isError)
            direct=await tool(client,'decide_application',{**args,'confirmed':True})
            check('direct unpreviewed confirmation denied',direct['code']=='confirmation_required')
            proposal=await tool(client,'decide_application',args)
            check('decision proposal does not mutate application',proposal['code']=='confirmation_required' and query('SELECT status FROM applications WHERE id=%s',(a,))==[('PENDING',)])
            strict=await client.call_tool('decide_application',{**args,'confirmed':'true','confirmation_token':proposal['confirmation_token']})
            check('confirmation requires a real boolean',strict.isError)
            changed=await tool(client,'decide_application',{**args,'reason':'Changed reason','confirmed':True,'confirmation_token':proposal['confirmation_token']})
            check('confirmation bound to exact reason',changed['code']=='confirmation_required')
            result=await tool(client,'decide_application',{**args,'confirmed':True,'confirmation_token':proposal['confirmation_token'],'officer_username':'forged'})
            check('approval uses authenticated officer',result['ok'] and result['decided_by']=='admin')
            check('approval reason and actor persisted',query("SELECT actor,note FROM audit_log WHERE application_id=%s AND action='APPROVED'",(a,))==[('admin:admin',args['reason'])])
            repeated=await tool(client,'decide_application',{**args,'confirmed':True,'confirmation_token':proposal['confirmation_token']})
            check('replayed decision cannot overwrite',not repeated['ok'] and query('SELECT count(*) FROM audit_log WHERE application_id=%s',(a,))[0][0]==2)
            viewb=await tool(client,'get_application',{'application_id':b})
            bargs={'application_id':b,'decision':'REJECTED','reason':'Proof mismatch in synthetic case','review_token':viewb['review_token']}
            pb=await tool(client,'decide_application',bargs)
            rb=await tool(client,'decide_application',{**bargs,'confirmed':True,'confirmation_token':pb['confirmation_token']})
            check('rejection recorded with reason',rb['ok'] and query('SELECT status FROM applications WHERE id=%s',(b,))==[('REJECTED',)])
            vc=await tool(client,'get_application',{'application_id':competing})
            args1={'application_id':competing,'decision':'APPROVED','reason':'Concurrent approval','review_token':vc['review_token']}
            p1=await tool(client,'decide_application',args1)
            vc2=await tool(client,'get_application',{'application_id':competing})
            args2={'application_id':competing,'decision':'REJECTED','reason':'Concurrent rejection','review_token':vc2['review_token']}
            p2=await tool(client,'decide_application',args2)
            results=await asyncio.gather(tool(client,'decide_application',{**args1,'confirmed':True,'confirmation_token':p1['confirmation_token']}),tool(client,'decide_application',{**args2,'confirmed':True,'confirmation_token':p2['confirmation_token']}))
            check('competing MCP decisions have exactly one winner',sum(r['ok'] for r in results)==1 and query('SELECT count(*) FROM audit_log WHERE application_id=%s',(competing,))[0][0]==2)
            vw=await tool(client,'get_application',{'application_id':withdrawn})
            wargs={'application_id':withdrawn,'decision':'APPROVED','reason':'Pending withdrawal race','review_token':vw['review_token']}
            pw=await tool(client,'decide_application',wargs)
            s.withdraw_pending_application(withdrawn,wm)
            rw=await tool(client,'decide_application',{**wargs,'confirmed':True,'confirmation_token':pw['confirmation_token']})
            check('withdrawn case cannot be decided',rw['code']=='not_pending')
            vd=await tool(client,'get_application',{'application_id':deemed})
            dargs={'application_id':deemed,'decision':'REJECTED','reason':'Competing statutory approval','review_token':vd['review_token']}
            pd=await tool(client,'decide_application',dargs)
            query('UPDATE applications SET submitted_at=%s WHERE id=%s RETURNING id',(datetime.now()-timedelta(days=16),deemed))
            job=subprocess.run([sys.executable,'/app/scripts/deemed_approval.py'],capture_output=True,text=True,timeout=30)
            check('unchanged statutory job approves overdue fixture',job.returncode==0 and query('SELECT status FROM applications WHERE id=%s',(deemed,))==[('DEEMED_APPROVED',)])
            rd=await tool(client,'decide_application',{**dargs,'confirmed':True,'confirmation_token':pd['confirmation_token']})
            check('deemed approval cannot be overwritten',rd['code']=='not_pending')
            summary=await tool(client,'get_queue_summary')
            finish=summary['finish_sign_in_url']
    # Verify visibility in the unmodified officer web portal.
    web=requests.Session()
    web.post(BASE+'/admin',data={'username':'admin','password':os.environ['ADMIN_PASSWORD']},timeout=20)
    check('MCP decision visible in officer web portal','APPROVED' in web.get(BASE+f'/admin/application/{a}',timeout=20).text)
    page=browser.get(finish,timeout=20)
    csrf=re.search(r'name="csrf" value="([^"]+)"',page.text).group(1)
    check('officer browser sign-out',browser.post(finish,data={'csrf':csrf},timeout=20).status_code==200)
    check('officer access immediately revoked after sign-out',request(storage.tokens.access_token).status_code==401)
    s.withdraw_pending_application(hidden,hm)
    # A second SDK client exercises refresh and access revocation independent of browser logout.
    auth2, store2, browser2=make_auth()
    async with streamablehttp_client(RESOURCE,auth=auth2) as (read,write,_):
        async with ClientSession(read,write) as client:
            await client.initialize()
            check('second officer client connects independently',len((await client.list_tools()).tools)==4)
    refreshed=browser2.post(BASE+'/oauth/token',data={'grant_type':'refresh_token','client_id':store2.client.client_id,'refresh_token':store2.tokens.refresh_token,'resource':RESOURCE},timeout=20)
    check('officer refresh rotates within fixed session',refreshed.status_code==200 and refreshed.json()['refresh_token']!=store2.tokens.refresh_token)
    newer=refreshed.json()
    browser2.post(BASE+'/oauth/revoke',data={'token':newer['refresh_token']},timeout=20)
    check('OAuth revocation immediately denies officer access',request(newer['access_token']).status_code==401)
    print(json.dumps({'summary':{'passed':len(checks),'failed':0},'synthetic_application_ids':[r[0] for r in fixtures]}),flush=True)


try:
    asyncio.run(main())
finally:
    for app_id,mobile in fixtures:
        s.withdraw_pending_application(app_id,mobile)
