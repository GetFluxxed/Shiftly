CREATE TABLE IF NOT EXISTS stores (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    access_code_hash CHAR(64) NOT NULL UNIQUE,
    crew_password_hash TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS manager_users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS store_memberships (
    manager_user_id BIGINT NOT NULL REFERENCES manager_users(id) ON DELETE CASCADE,
    store_id BIGINT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'manager',
    PRIMARY KEY (manager_user_id, store_id)
);

ALTER TABLE reports ADD COLUMN IF NOT EXISTS store_id BIGINT REFERENCES stores(id);
ALTER TABLE stores ADD COLUMN IF NOT EXISTS crew_password_hash TEXT;
ALTER TABLE manager_sessions ADD COLUMN IF NOT EXISTS manager_user_id BIGINT REFERENCES manager_users(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS reports_store_created_idx ON reports (store_id, created_at DESC);
