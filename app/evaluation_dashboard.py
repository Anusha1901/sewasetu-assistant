"""Public, read-only evaluation snapshot. No database, session or credential access."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from flask import Blueprint, Response, render_template
import services

web = Blueprint('evaluation', __name__)
EVIDENCE = Path(__file__).parent / 'evaluation/evidence.json'


@lru_cache(maxsize=1)
def load_evidence():
    raw = EVIDENCE.read_bytes()
    data = json.loads(raw)
    assert data['schema_version'] == 1
    assert len(data['checks']) == data['baseline']['passed'] + data['baseline']['failed']
    assert sum(c['scope'] == 'LOCAL' for c in data['checks']) == data['baseline']['local']
    assert sum(c['scope'] == 'LIVE' for c in data['checks']) == data['baseline']['live']
    assert sum(c['status'] == 'FAIL' for c in data['checks']) == data['baseline']['failed']
    return data, hashlib.sha256(raw).hexdigest()


@web.after_request
def public_evidence_headers(response):
    response.headers['Cache-Control'] = 'public, max-age=300'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = ("default-src 'none'; style-src 'self'; script-src 'self'; "
        "img-src 'self' data:; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
    return response


@web.get('/eval-dashboard')
def dashboard():
    data, digest = load_evidence()
    groups = {source['id']: [c for c in data['checks'] if c['source_id'] == source['id']]
              for source in data['sources']}
    lookup = {c['id']: c for c in data['checks']}
    return render_template('eval_dashboard.html', evidence=data, digest=digest, groups=groups,
                           lookup=lookup, rules={'age': services.MIN_AGE, 'sla': services.SLA_DAYS,
                           'deadline': services.SCHEME_DEADLINE.strftime('%d %B %Y, %H:%M IST'),
                           'window_open': services.now_ist() <= services.SCHEME_DEADLINE})


@web.get('/eval-dashboard/evidence.json')
def public_evidence():
    load_evidence()
    # Constant, reviewed file only; its exact bytes match the displayed SHA-256.
    return Response(EVIDENCE.read_bytes(), mimetype='application/json')
