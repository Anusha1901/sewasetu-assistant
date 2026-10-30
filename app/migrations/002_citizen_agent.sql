BEGIN;
-- Agent session and preparation state in the existing portal database.
CREATE TABLE IF NOT EXISTS oauth_agent_sessions (
    id VARCHAR(64) PRIMARY KEY,
    subject VARCHAR(80) NOT NULL,
    client_id VARCHAR(300) NOT NULL,
    audience VARCHAR(300) NOT NULL,
    expires_at BIGINT NOT NULL,
    revoked_at BIGINT
);
ALTER TABLE oauth_refresh_tokens ADD COLUMN IF NOT EXISTS agent_session_id VARCHAR(64);
CREATE TABLE IF NOT EXISTS citizen_drafts (
    id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES oauth_agent_sessions(id),
    subject VARCHAR(80) NOT NULL,
    data JSONB NOT NULL DEFAULT '{}',
    doc_path TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1,
    expires_at BIGINT NOT NULL,
    application_id INTEGER REFERENCES applications(id),
    declaration_accepted_at BIGINT
);
CREATE INDEX IF NOT EXISTS idx_citizen_draft_session ON citizen_drafts(session_id);
CREATE TABLE IF NOT EXISTS citizen_links (
    token_hash VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES oauth_agent_sessions(id),
    kind VARCHAR(20) NOT NULL,
    draft_id VARCHAR(64) REFERENCES citizen_drafts(id),
    application_id INTEGER REFERENCES applications(id),
    expires_at BIGINT NOT NULL
);
COMMIT;
