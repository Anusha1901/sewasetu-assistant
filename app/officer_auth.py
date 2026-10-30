"""Officer identity is derived exclusively from the portal's verified access token."""
from dataclasses import dataclass
from citizen_auth import ISSUER, verify_agent_token, require_agent_session

RESOURCE = ISSUER + '/mcp/officer'


@dataclass(frozen=True)
class Officer:
    subject: str
    session_id: str
    client_id: str
    expires_at: int

    @property
    def username(self):
        return self.subject.split(':', 1)[1]


def verify_officer_token(raw):
    return verify_agent_token(raw, 'officer', RESOURCE, Officer, r'officer:[^\s:]{1,44}')


def require_session(cur, actor):
    return require_agent_session(cur, actor, RESOURCE)
