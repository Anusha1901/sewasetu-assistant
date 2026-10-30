"""Session-bound browser proof review and sign-out for officer assistants."""
import io
import secrets
import time
from flask import Blueprint, request, session, render_template, abort, send_file

import services as s
import officer
import documents
from pathlib import PurePosixPath
from citizen_web import private_response

web = Blueprint('officer_web', __name__)
web.after_request(private_response)


@web.route('/officer/<kind>/<token>', methods=['GET', 'POST'])
def handoff(kind, token):
    if kind not in ('proof', 'ack', 'finish'):
        abort(404)
    try:
        with s.transaction() as cur:
            actor, app_id, expected_hash = officer.resolve_link(cur, token, kind, session.get('officer_verified'))
            if kind == 'finish':
                csrf = session.setdefault('officer_csrf', secrets.token_urlsafe(32))
                if request.method == 'POST':
                    if not secrets.compare_digest(csrf, request.form.get('csrf', '')):
                        abort(403)
                    cur.execute('UPDATE oauth_agent_sessions SET revoked_at=%s WHERE id=%s', (int(time.time()), actor.session_id))
                    cur.execute('UPDATE oauth_refresh_tokens SET revoked_at=%s WHERE agent_session_id=%s', (s.datetime.now(), actor.session_id))
                    session.clear()
                    return render_template('officer_handoff.html', finished=True)
                return render_template('officer_handoff.html', csrf=csrf, username=actor.username)
            if request.method != 'GET':
                abort(405)
            row = officer._case(cur, actor, app_id)
            if kind == 'ack':
                from app import generate_acknowledgment
                return send_file(io.BytesIO(generate_acknowledgment(cur, app_id)), mimetype='application/pdf',
                                 as_attachment=True, download_name='acknowledgment.pdf')
            path, digest = officer.proof_info(row[10])
            if not path or not expected_hash or not secrets.compare_digest(digest, expected_hash):
                raise officer.OfficerError('proof_changed', 'Proof is unavailable or changed. Inspect the case again.')
            return send_file(io.BytesIO(documents.read(path)), mimetype='application/octet-stream', as_attachment=True,
                             download_name='age-proof' + PurePosixPath(str(path)).suffix.lower())
    except officer.OfficerError as exc:
        return render_template('officer_handoff.html', error=str(exc)), 403 if exc.code in ('browser_sign_in_required', 'sign_in_required', 'not_found') else 410
