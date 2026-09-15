CREATE TABLE IF NOT EXISTS manager_sessions (
    token_hash CHAR(64) PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS manager_sessions_expiry_idx ON manager_sessions (expires_at);
