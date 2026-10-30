"""Browser-only upload, acknowledgment and finish actions for OAuth citizens."""
import hashlib
import io
import os
import secrets
import time
from pathlib import Path

from flask import Blueprint, request, session, render_template, abort, send_file
import citizen
import services as s
import documents

web = Blueprint('citizen_web', __name__)


@web.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response


@web.route('/citizen/<kind>/<token>', methods=['GET', 'POST'])
def handoff(kind, token):
    if kind not in ('upload', 'ack', 'finish'):
        abort(404)
    try:
        with s.transaction() as cur:
            actor, draft_id, app_id = citizen.resolve_link(cur, token, kind, session.get('citizen_verified'))
            csrf = session.get('citizen_csrf')
            if not csrf:
                csrf = secrets.token_urlsafe(32)
                session['citizen_csrf'] = csrf
            if request.method == 'POST':
                if not secrets.compare_digest(request.form.get('csrf', ''), csrf):
                    abort(403)
            if kind == 'ack':
                if request.method != 'GET':
                    abort(405)
                row = s.get_citizen_application(app_id, actor.mobile)
                if not row or row[5] not in citizen.supported_blocks():
                    abort(404)
                from app import generate_acknowledgment
                return send_file(io.BytesIO(generate_acknowledgment(cur, app_id)), mimetype='application/pdf',
                                 as_attachment=True, download_name='acknowledgment.pdf')
            if kind == 'finish':
                if request.method == 'POST':
                    cur.execute('UPDATE oauth_agent_sessions SET revoked_at=%s WHERE id=%s', (int(time.time()), actor.session_id))
                    cur.execute('UPDATE oauth_refresh_tokens SET revoked_at=%s WHERE agent_session_id=%s', (s.datetime.now(), actor.session_id))
                    session.clear()
                    return render_template('citizen_handoff.html', finished=True)
                return render_template('citizen_handoff.html', kind=kind, csrf=csrf, masked=actor.mobile[-4:])
            data, _, revision, _, app_id = citizen._draft(cur, actor, draft_id)
            if app_id:
                raise citizen.CitizenError('already_submitted', 'This application has already been submitted.')
            if data.get('block', '').strip() not in citizen.supported_blocks():
                raise citizen.CitizenError('unsupported_block', 'Prepare an application in a supported block first.')
            if request.method == 'GET':
                return render_template('citizen_handoff.html', kind=kind, csrf=csrf, masked=actor.mobile[-4:])
            f = request.files.get('document')
            if f is None:
                raise citizen.CitizenError('document_required', 'Choose an age proof file.')
            content = f.read(citizen.MAX_FILE + 1)
            suffix = citizen.validate_document(f.filename, content)
            folder = Path(s.config.get('app', 'upload_dir')) / 'agent'
            path = folder / (secrets.token_hex(24) + suffix)
            reference = documents.save(content, suffix, local_path=path)
            try:
                cur.execute('UPDATE citizen_drafts SET doc_path=%s,revision=%s WHERE id=%s', (reference, revision + 1, draft_id))
                cur.execute('DELETE FROM citizen_links WHERE token_hash=%s', (hashlib.sha256(token.encode()).hexdigest(),))
            except Exception:
                documents.delete(reference)
                raise
            return render_template('citizen_handoff.html', uploaded=True)
    except citizen.CitizenError as exc:
        return render_template('citizen_handoff.html', error=str(exc)), 403 if exc.code in ('browser_sign_in_required', 'sign_in_required') else 410


@web.before_request
def limit_upload_request():
    # Browser multipart uploads supply Content-Length. Bound parsing before request.files.
    if request.method == 'POST' and request.path.startswith('/citizen/upload/'):
        if request.content_length is None:
            abort(411)
        if request.content_length > citizen.MAX_FILE + 65536:
            abort(413)
