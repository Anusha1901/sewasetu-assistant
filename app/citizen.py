"""Citizen agent preparation and browser handoffs; pension rules stay in services."""
import hashlib
import io
import json
import os
import secrets
import time
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from psycopg2.extras import Json

import services as s
import documents
from citizen_auth import Citizen, ISSUER, RESOURCE, require_session

MAX_FILE = 5 * 1024 * 1024
DECLARATION = ('I declare that the information furnished is true to the best of my knowledge '
               'and belief. I understand that false information may result in cancellation of pension.')
FIELDS = {'applicant_name', 'dob', 'gender', 'marital_status', 'husband_name',
          'village', 'block', 'bank_account', 'ifsc'}
WIDTHS = {'applicant_name': 100, 'village': 100, 'block': 50, 'gender': 10,
          'marital_status': 20, 'husband_name': 100, 'bank_account': 30, 'ifsc': 15, 'dob': 10}


class CitizenError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def supported_blocks():
    blocks = tuple(dict.fromkeys(b.strip() for b in os.environ.get('CITIZEN_MCP_BLOCKS', 'Sonari,Rajapara').split(',') if b.strip()))
    if not blocks or any(b not in s.BLOCKS for b in blocks):
        raise RuntimeError('CITIZEN_MCP_BLOCKS must contain configured portal block names')
    return blocks


def verify_configured_blocks():
    blocks = supported_blocks()
    with s.transaction() as cur:
        cur.execute('SELECT DISTINCT block FROM applications WHERE block IN %s', (blocks,))
        found = {r[0] for r in cur.fetchall()}
    if set(blocks) != found:
        raise RuntimeError('Configured citizen agent blocks are absent from the database')


def _live(cur, actor):
    try:
        return require_session(cur, actor)
    except ValueError as exc:
        raise CitizenError('sign_in_required', str(exc)) from exc


def _link(cur, actor, kind, draft_id=None, app_id=None):
    end = _live(cur, actor)
    token = secrets.token_urlsafe(32)
    cur.execute('INSERT INTO citizen_links(token_hash,session_id,kind,draft_id,application_id,expires_at) '
                'VALUES (%s,%s,%s,%s,%s,%s)',
                (hashlib.sha256(token.encode()).hexdigest(), actor.session_id, kind, draft_id, app_id,
                 min(int(time.time()) + 900, end)))
    return ISSUER + '/citizen/' + kind + '/' + token


def scheme_info(actor):
    with s.transaction() as cur:
        _live(cur, actor)
        finish = _link(cur, actor, 'finish')
    return {'ok': True, 'scheme': 'Old Age Pension', 'monthly_pension_rupees': 250,
            'minimum_age': s.MIN_AGE, 'processing_sla_days': s.SLA_DAYS,
            'deadline_ist': s.SCHEME_DEADLINE.isoformat(), 'window_open': s.now_ist() <= s.SCHEME_DEADLINE,
            'agent_supported_blocks': supported_blocks(), 'portal_blocks': s.BLOCKS,
            'requirements': ['name', 'DOB DD/MM/YYYY', 'village', 'block', 'bank account', 'age proof'],
            'age_proof': 'Birth certificate, school leaving certificate or Voter ID; JPG/PNG/PDF, up to 5 MB',
            'identity': 'Verified mobile ending ' + actor.mobile[-4:],
            'shared_phone_notice': 'One active application per mobile. To help another person, finish this sign-in and reconnect. Never share OTPs or passwords with the assistant.',
            'finish_sign_in_url': finish}


def _draft(cur, actor, draft_id):
    _live(cur, actor)
    cur.execute('SELECT data,doc_path,revision,expires_at,application_id FROM citizen_drafts '
                'WHERE id=%s AND session_id=%s AND subject=%s FOR UPDATE',
                (draft_id, actor.session_id, actor.subject))
    row = cur.fetchone()
    if not row:
        raise CitizenError('not_found', 'Preparation not found in this sign-in.')
    if row[3] <= time.time():
        raise CitizenError('expired_preparation', 'Preparation expired. Prepare a new application.')
    return row


def prepare(actor, details=None, draft_id=None):
    details = details or {}
    if set(details) - FIELDS:
        raise CitizenError('invalid_fields', 'Use only application fields; identity comes from sign-in.')
    for key, value in details.items():
        if not isinstance(value, str) or len(value) > WIDTHS[key]:
            raise CitizenError('invalid_details', key + ' must be text of at most ' + str(WIDTHS[key]) + ' characters.')
    with s.transaction() as cur:
        end = _live(cur, actor)
        if draft_id:
            old, doc, revision, _, app_id = _draft(cur, actor, draft_id)
            if app_id:
                raise CitizenError('already_submitted', 'This preparation has already been submitted.')
            values = {**old, **details}
            if values != old:
                revision += 1
                cur.execute('UPDATE citizen_drafts SET data=%s,revision=%s WHERE id=%s', (Json(values), revision, draft_id))
        else:
            draft_id, values, doc, revision = secrets.token_urlsafe(24), details, '', 1
            cur.execute('INSERT INTO citizen_drafts(id,session_id,subject,data,expires_at) VALUES (%s,%s,%s,%s,%s)',
                        (draft_id, actor.session_id, actor.subject, Json(values), end))
        errors, cleaned = s.validate_application(values, doc)
        if cleaned['block'] and cleaned['block'] not in supported_blocks():
            errors.append('Agent applications are supported only in: ' + ', '.join(supported_blocks()))
        if doc and not documents.exists(doc):
            errors.append('The age proof is unavailable. Upload it again.')
        existing = s.active_application(cur, actor.mobile)
        if existing:
            errors.append('An active application already exists: ' + existing[1])
        preview = {key: value for key, value in cleaned.items() if key not in ('doc_path', 'husband_employer')}
        preview['dob'] = cleaned['dob'].strftime('%d/%m/%Y') if cleaned['dob'] else values.get('dob', '')
        upload_url = _link(cur, actor, 'upload', draft_id=draft_id)
        finish = _link(cur, actor, 'finish')
    return {'ok': True, 'draft_id': draft_id, 'revision': revision, 'preview': preview,
            'identity': 'Verified mobile ending ' + actor.mobile[-4:],
            'has_age_proof': bool(doc), 'ready_to_submit': not errors, 'errors': errors,
            'upload_url': upload_url, 'finish_sign_in_url': finish, 'declaration': DECLARATION,
            'next_action': 'Show this preview and declaration. Submit only after explicit acceptance of this revision.' if not errors else 'Correct the errors or open upload_url in the browser used to sign in, then call prepare_application again.'}


def submit(actor, draft_id, revision, declaration_accepted):
    if declaration_accepted is not True:
        raise CitizenError('declaration_required', 'Explicit acceptance of the displayed declaration is required.')
    with s.transaction() as cur:
        values, doc, current, _, app_id = _draft(cur, actor, draft_id)
        if revision != current:
            raise CitizenError('stale_preview', 'Details or document changed. Prepare again and accept the current preview.')
        if app_id:
            cur.execute('SELECT application_no FROM applications WHERE id=%s AND mobile=%s', (app_id, actor.mobile))
            return {'ok': True, 'application_id': app_id, 'application_no': cur.fetchone()[0], 'already_submitted': True}
        if values.get('block', '').strip() not in supported_blocks():
            raise CitizenError('unsupported_block', 'Agent applications are supported only in: ' + ', '.join(supported_blocks()))
        if not doc or not documents.exists(doc):
            raise CitizenError('document_required', 'Upload a valid age proof first.')
        try:
            app_id, app_no = s.submit_application(actor.mobile, values, doc, cur=cur)
        except s.ValidationError as exc:
            raise CitizenError('invalid_application', str(exc)) from exc
        except s.DuplicateApplication as exc:
            raise CitizenError('duplicate_application', 'An active application already exists: ' + exc.existing[1]) from exc
        cur.execute('UPDATE citizen_drafts SET application_id=%s,declaration_accepted_at=%s WHERE id=%s',
                    (app_id, int(time.time()), draft_id))
        # Every upload capability for this preparation becomes unusable after commit.
        cur.execute("DELETE FROM citizen_links WHERE draft_id=%s AND kind='upload'", (draft_id,))
        ack = _link(cur, actor, 'ack', app_id=app_id)
    from app import send_sms
    send_sms(actor.mobile, 'Sewa Setu: application %s received. Track at the status portal with mobile no. and password (DOB as DDMMYYYY).' % app_no)
    return {'ok': True, 'application_id': app_id, 'application_no': app_no, 'status': 'PENDING',
            'acknowledgment_url': ack, 'already_submitted': False}


def my_applications(actor, before_id=None):
    with s.transaction() as cur:
        _live(cur, actor)
    rows = s.list_citizen_applications(actor.mobile, supported_blocks(), before_id=before_id)
    out = []
    with s.transaction() as cur:
        for row in rows:
            app_id, number, name, block, status, submitted, decided, bank = row
            audit = s.get_audit(app_id)
            reason = next((e[3] for e in reversed(audit) if e[1] in ('APPROVED', 'REJECTED', 'DEEMED_APPROVED')), '')
            out.append({'application_id': app_id, 'application_no': number, 'applicant_name': name,
                        'block': block, 'status': status, 'submitted_at': str(submitted),
                        'decided_at': str(decided) if decided else None, 'decision_reason': reason,
                        'bank_account_last4': (bank or '')[-4:],
                        'acknowledgment_url': _link(cur, actor, 'ack', app_id=app_id)})
        finish = _link(cur, actor, 'finish')
    return {'ok': True, 'applications': out, 'next_before_id': rows[-1][0] if len(rows) == 20 else None,
            'agent_supported_blocks': supported_blocks(), 'finish_sign_in_url': finish}


def withdraw(actor, application_id, confirmed):
    with s.transaction() as cur:
        _live(cur, actor)
    row = s.get_citizen_application(application_id, actor.mobile)
    if not row or row[5] not in supported_blocks():
        raise CitizenError('not_found', 'Application not found within your supported blocks.')
    if confirmed is not True:
        return {'ok': False, 'code': 'confirmation_required', 'message': 'Ask the citizen to confirm withdrawal of ' + row[0]}
    number = s.withdraw_pending_application(application_id, actor.mobile)
    if not number:
        raise CitizenError('not_pending', 'Only a pending application can be withdrawn.')
    return {'ok': True, 'application_no': number, 'status': 'WITHDRAWN'}


def validate_document(filename, content):
    suffix = Path(filename or '').suffix.lower()
    if not content or len(content) > MAX_FILE:
        raise CitizenError('invalid_document', 'Choose a nonempty file up to 5 MB.')
    try:
        if suffix == '.pdf':
            if not content.startswith(b'%PDF-'):
                raise ValueError('Not a PDF')
            pdf = PdfReader(io.BytesIO(content), strict=True)
            if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 100:
                raise ValueError('Encrypted or excessive pages')
            root = pdf.trailer['/Root']
            names = root.get('/Names', {})
            if hasattr(names, 'get_object'):
                names = names.get_object()
            action = root.get('/OpenAction')
            if hasattr(action, 'get_object'):
                action = action.get_object()
            # Normal page/zoom destinations (including FPDF's default) are safe.
            active_open = isinstance(action, dict) and action.get('/S') not in (None, '/GoTo')
            if active_open or '/AA' in root or any(k in names for k in ['/JavaScript', '/EmbeddedFiles']) or any('/AA' in page for page in pdf.pages):
                raise ValueError('Active PDF content')
            return '.pdf'
        if suffix not in ('.jpg', '.jpeg', '.png'):
            raise ValueError('Unsupported extension')
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in ('JPEG', 'PNG') or image.width * image.height > 25000000:
                raise ValueError('Invalid image')
            if (suffix == '.png') != (image.format == 'PNG'):
                raise ValueError('Extension mismatch')
            image.verify()
        return '.png' if suffix == '.png' else '.jpg'
    except Exception as exc:
        raise CitizenError('invalid_document', 'Upload a valid, unencrypted JPG, PNG or PDF age proof.') from exc


def resolve_link(cur, token, kind, verified):
    cur.execute('SELECT l.session_id,l.draft_id,l.application_id,l.expires_at,s.subject,s.client_id,s.expires_at '
                'FROM citizen_links l JOIN oauth_agent_sessions s ON s.id=l.session_id '
                'WHERE l.token_hash=%s AND l.kind=%s FOR UPDATE OF l',
                (hashlib.sha256(token.encode()).hexdigest(), kind))
    row = cur.fetchone()
    if not row or row[3] <= time.time():
        raise CitizenError('expired_link', 'This link is unavailable or expired. Ask the assistant for a new link.')
    if not verified or verified.get('subject') != row[4] or verified.get('at', 0) + 7200 <= time.time():
        raise CitizenError('browser_sign_in_required', 'Open this link in the browser used for citizen OAuth sign-in. If needed, reconnect the assistant and sign in again.')
    actor = Citizen(row[4], row[0], row[5], row[6])
    _live(cur, actor)
    return actor, row[1], row[2]
