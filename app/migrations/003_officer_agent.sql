BEGIN;
-- Officer review/confirmation state in the existing portal database.
CREATE TABLE IF NOT EXISTS officer_reviews (
    token_hash VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES oauth_agent_sessions(id),
    application_id INTEGER NOT NULL REFERENCES applications(id),
    snapshot VARCHAR(64) NOT NULL,
    expires_at BIGINT NOT NULL,
    proposed_status VARCHAR(20),
    reason VARCHAR(500),
    confirmation_hash VARCHAR(64),
    consumed_at BIGINT
);
CREATE TABLE IF NOT EXISTS officer_links (
    token_hash VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES oauth_agent_sessions(id),
    application_id INTEGER REFERENCES applications(id),
    kind VARCHAR(20) NOT NULL,
    proof_hash VARCHAR(64),
    expires_at BIGINT NOT NULL
);
COMMIT;
