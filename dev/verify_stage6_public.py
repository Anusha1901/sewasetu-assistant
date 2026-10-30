"""Unauthenticated dashboard checks; print assertions only, never private canaries."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import requests


def run(base):
    checks = []
    def check(name, passed):
        checks.append({'check': name, 'passed': bool(passed)})
        print(json.dumps(checks[-1]), flush=True)
        assert passed, name
    root = Path(__file__).resolve().parents[1]
    expected_raw = (root / 'app/evaluation/evidence.json').read_bytes()
    expected = json.loads(expected_raw)
    session = requests.Session()
    page = session.get(base + '/eval-dashboard', timeout=120)
    check('dashboard is publicly accessible without a cookie or token', page.status_code == 200)
    response = session.get(base + '/eval-dashboard/evidence.json', timeout=120)
    check('public sanitized evidence export returns JSON', response.status_code == 200 and 'application/json' in response.headers.get('Content-Type', ''))
    check('deployed evidence equals the reviewed local snapshot', response.json() == expected)
    check('download bytes match the displayed snapshot digest', response.content == expected_raw and hashlib.sha256(expected_raw).hexdigest() in page.text)
    check('summary remains the historical 376-check baseline', expected['baseline']['passed'] == 376 and len(expected['checks']) == 376 and '376' in page.text)
    check('local and live results are separately labeled', '275' in page.text and '101' in page.text and 'local regression checks' in page.text and 'live deployment checks' in page.text)
    check('all untested scenarios remain labeled not tested', len([r for r in expected['scenarios'] if r['status'] == 'NOT TESTED']) == 3 and 'NOT TESTED' in page.text)
    check('real Codex excerpts are distinguished from SDK fixtures', 'verbatim excerpt' in page.text and 'not three independent AI conversations' in page.text)
    check('no OTPs tokens passwords banks or document paths are exported as fields', not re.search(r'"(?:mobile|bank_account|password|access_token|refresh_token|doc_path)"\s*:', response.text))
    check('no private capability URLs are exported', not re.search(r'https?://[^\s"]+/(?:citizen|officer)/(?:upload|proof|ack|finish)/[\w-]+', response.text))
    check('no full telephone numbers appear in public evidence', not re.search(r'\b\d{10}\b', response.text))
    private = root / 'deploy/secrets/render.env'
    if private.exists():
        values = dict(line.split('=',1) for line in private.read_text().splitlines() if '=' in line)
        check('real deployment secrets are absent from public responses', all(values[key] not in page.text + response.text for key in ['SECRET_KEY','ADMIN_PASSWORD','DATABASE_URL','SUPABASE_SERVICE_ROLE_KEY']))
    check('evidence query cannot select other files or records', session.get(base+'/eval-dashboard/evidence.json?application_id=1&path=../../config/app.ini',timeout=120).content == response.content)
    check('dashboard and export reject state-changing POST requests', all(session.post(base+path,json={'status':'APPROVED'},timeout=120).status_code == 405 for path in ['/eval-dashboard','/eval-dashboard/evidence.json']))
    check('dashboard creates no authentication cookies', 'Set-Cookie' not in page.headers and 'Set-Cookie' not in response.headers)
    check('dashboard has restrictive script connection and frame policy', all(value in page.headers.get('Content-Security-Policy','') for value in ["default-src 'none'","connect-src 'none'","frame-ancestors 'none'"]))
    check('public responses prevent MIME sniffing and referrer leakage', page.headers.get('X-Content-Type-Options') == 'nosniff' and page.headers.get('Referrer-Policy') == 'no-referrer')
    check('self-hosted stylesheet and script load', all(session.get(base+'/static/'+name,timeout=120).status_code == 200 for name in ['eval-dashboard.css','eval-dashboard.js']))
    check('the existing portal links to the evaluation dashboard', '/eval-dashboard' in session.get(base+'/',timeout=120).text)
    check('scheme deadline and statutory SLA are unchanged on the dashboard', '31 October 2026, 23:59 IST' in page.text and '15-day deemed approval' in page.text)
    print(json.dumps({'summary': {'passed':len(checks),'failed':0}}),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',required=True)
    run(parser.parse_args().base_url.rstrip('/'))
