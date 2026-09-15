ALTER TABLE stores ADD COLUMN IF NOT EXISTS crew_password_hash TEXT;

CREATE TABLE IF NOT EXISTS crew_sessions (
    token_hash CHAR(64) PRIMARY KEY,
    store_id BIGINT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS crew_sessions_expiry_idx ON crew_sessions (expires_at);
