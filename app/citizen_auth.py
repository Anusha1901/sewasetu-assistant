"""Citizen resource authentication and session checks; no assistant-supplied identity."""
import os
import re
import time
from urllib.parse import urlparse
from dataclasses import dataclass

import jwt
import services as s

ISSUER = os.environ.get('PUBLIC_BASE_URL', 'http://localhost:8000').rstrip('/')
RESOURCE = ISSUER + '/mcp/citizen'


def validate_public_configuration(issuer, secret, local_console, admin_password):
    if urlparse(issuer).hostname in ('localhost', '127.0.0.1'):
        return
    if not issuer.startswith('https://') or len(secret) < 32:
        raise RuntimeError('Public deployment requires HTTPS PUBLIC_BASE_URL and a random SECRET_KEY of at least 32 characters')
    if local_console == '1':
        raise RuntimeError('Public deployment must not enable the unauthenticated local SMS console')
    if not admin_password or admin_password == 'change-me-before-deploying':
        raise RuntimeError('Public deployment requires a private ADMIN_PASSWORD')


@dataclass(frozen=True)
class Citizen:
    subject: str
    session_id: str
    client_id: str
    expires_at: int

    @property
    def mobile(self):
        return self.subject.split(':', 1)[1]


def require_session(cur, citizen):
    return require_agent_session(cur, citizen, RESOURCE)


def require_agent_session(cur, citizen, resource):
    now = int(time.time())
    if citizen.expires_at <= now:
        raise ValueError('Sign-in expired. Reconnect and sign in again.')
    cur.execute('SELECT expires_at FROM oauth_agent_sessions WHERE id=%s AND subject=%s '
                'AND client_id=%s AND audience=%s AND revoked_at IS NULL AND expires_at>%s',
                (citizen.session_id, citizen.subject, citizen.client_id, resource, now))
    row = cur.fetchone()
    if not row:
        raise ValueError('Sign-in expired or ended. Reconnect and sign in again.')
    return row[0]


def verify_citizen_token(raw):
    return verify_agent_token(raw, "citizen", RESOURCE, Citizen, r"citizen:[0-9]{10}")


def verify_agent_token(raw, role, resource, actor_type, subject_pattern):
    # Same-process verifier uses only the portal's published public key material.
    from oauth import public_jwks
    try:
        header = jwt.get_unverified_header(raw)
        keys = [key for key in public_jwks()['keys'] if key['kid'] == header.get('kid')]
        if len(keys) != 1:
            return None
        claims = jwt.decode(raw, jwt.PyJWK.from_dict(keys[0]).key, algorithms=['RS256'],
                            issuer=ISSUER, audience=resource,
                            options={'require': ['exp', 'iat', 'iss', 'aud', 'sub', 'sid', 'client_id', 'session_ends']})
        if (claims.get('role') != role or claims.get('scope') != role
                or claims.get('kind') != 'access'
                or not re.fullmatch(subject_pattern, claims['sub'])
                or claims['session_ends'] <= time.time()):
            return None
        citizen = actor_type(claims['sub'], claims['sid'], claims['client_id'], claims['exp'])
        with s.transaction() as cur:
            require_agent_session(cur, citizen, resource)
        return citizen
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        return None


def revoke_sessions(cur, subject, token_hash=None):
    if token_hash:
        cur.execute('UPDATE oauth_agent_sessions SET revoked_at=%s WHERE subject=%s AND id IN '
                    '(SELECT agent_session_id FROM oauth_refresh_tokens WHERE token_hash=%s)',
                    (int(time.time()), subject, token_hash))
    else:
        cur.execute('UPDATE oauth_agent_sessions SET revoked_at=%s WHERE subject=%s AND revoked_at IS NULL',
                    (int(time.time()), subject))
