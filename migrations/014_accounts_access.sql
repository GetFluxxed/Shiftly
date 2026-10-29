-- Additive named identity. No inferred business, ownership, or historical crew identity.
CREATE FUNCTION account_username_key(value TEXT) RETURNS TEXT
LANGUAGE SQL IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT lower(btrim(regexp_replace(normalize(value, NFKC), '[[:space:]]+', ' ', 'g')))
$$;

CREATE TABLE businesses (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 120),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE stores ADD COLUMN business_id BIGINT REFERENCES businesses(id);
ALTER TABLE stores ADD COLUMN accounts_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE stores ADD COLUMN shared_crew_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE stores ADD CONSTRAINT stores_business_identity UNIQUE (id, business_id);

CREATE TABLE account_users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL CHECK (char_length(btrim(username)) BETWEEN 2 AND 80),
    username_key TEXT GENERATED ALWAYS AS (account_username_key(username)) STORED UNIQUE,
    display_name TEXT NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 1 AND 120),
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'pending', 'suspended')),
    credential_version BIGINT NOT NULL DEFAULT 1 CHECK (credential_version > 0),
    legacy_manager_id BIGINT UNIQUE REFERENCES manager_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE business_memberships (
    user_id BIGINT NOT NULL REFERENCES account_users(id),
    business_id BIGINT NOT NULL REFERENCES businesses(id),
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin')),
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'revoked')),
    capabilities TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, business_id),
    CHECK (capabilities <@ ARRAY['reports.submit','reports.view','reports.manage','inventory.view','counts.submit','counts.approve','receipts.draft','receipts.post','stock.adjust','configuration.manage','catalog.propose','catalog.manage','memberships.manage']::TEXT[])
);
CREATE TABLE account_store_memberships (
    user_id BIGINT NOT NULL REFERENCES account_users(id),
    store_id BIGINT NOT NULL REFERENCES stores(id),
    business_id BIGINT REFERENCES businesses(id),
    role TEXT NOT NULL CHECK (role IN ('manager', 'crew', 'admin')),
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'revoked')),
    capabilities TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, store_id),
    FOREIGN KEY (store_id, business_id) REFERENCES stores(id, business_id),
    CHECK (role <> 'admin' OR business_id IS NOT NULL),
    CHECK (capabilities <@ ARRAY['reports.submit','reports.view','reports.manage','inventory.view','counts.submit','counts.approve','receipts.draft','receipts.post','stock.adjust','configuration.manage','catalog.propose','catalog.manage','memberships.manage']::TEXT[]),
    CHECK (role <> 'crew' OR capabilities <@ ARRAY['reports.submit','inventory.view','counts.submit','receipts.draft','catalog.propose']::TEXT[]),
    CHECK (role <> 'manager' OR NOT ('catalog.manage' = ANY(capabilities)))
);
CREATE INDEX account_store_memberships_scope_idx ON account_store_memberships (store_id, state);
CREATE TABLE account_sessions (
    token_hash CHAR(64) PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES account_users(id),
    store_id BIGINT NOT NULL REFERENCES stores(id),
    credential_version BIGINT NOT NULL CHECK (credential_version > 0),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX account_sessions_user_idx ON account_sessions (user_id, store_id);
CREATE INDEX account_sessions_expiry_idx ON account_sessions (expires_at);
CREATE TABLE account_audit (
    id BIGSERIAL PRIMARY KEY,
    actor_user_id BIGINT REFERENCES account_users(id),
    subject_user_id BIGINT REFERENCES account_users(id),
    business_id BIGINT REFERENCES businesses(id),
    store_id BIGINT REFERENCES stores(id),
    action TEXT NOT NULL CHECK (char_length(action) BETWEEN 1 AND 100),
    reason TEXT NOT NULL DEFAULT '',
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX account_audit_scope_idx ON account_audit (store_id, created_at DESC);
CREATE TABLE account_invitations (
    id UUID PRIMARY KEY,
    token_hash CHAR(64) NOT NULL UNIQUE,
    user_id BIGINT NOT NULL REFERENCES account_users(id),
    store_id BIGINT NOT NULL REFERENCES stores(id),
    business_id BIGINT REFERENCES businesses(id),
    role TEXT NOT NULL CHECK (role IN ('manager', 'crew')),
    capabilities TEXT[] NOT NULL DEFAULT '{}',
    created_by BIGINT NOT NULL REFERENCES account_users(id),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (store_id, business_id) REFERENCES stores(id, business_id),
    CHECK (capabilities <@ ARRAY['reports.submit','reports.view','reports.manage','inventory.view','counts.submit','counts.approve','receipts.draft','receipts.post','stock.adjust','configuration.manage','catalog.propose','memberships.manage']::TEXT[]),
    CHECK (role <> 'crew' OR capabilities <@ ARRAY['reports.submit','inventory.view','counts.submit','receipts.draft','catalog.propose']::TEXT[])
);
CREATE TABLE account_password_resets (
    id UUID PRIMARY KEY,
    token_hash CHAR(64) NOT NULL UNIQUE,
    user_id BIGINT NOT NULL REFERENCES account_users(id),
    credential_version BIGINT NOT NULL CHECK (credential_version > 0),
    created_by BIGINT REFERENCES account_users(id),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- A normalization collision fails this transaction rather than merging two people.
-- Existing PBKDF2 salt/hash pairs remain byte-for-byte unchanged.
INSERT INTO account_users (username, display_name, password_salt, password_hash, state, legacy_manager_id, created_at)
SELECT username, username, password_salt, password_hash,
       CASE WHEN active THEN 'active' ELSE 'suspended' END, id, created_at
FROM manager_users ORDER BY id;
INSERT INTO account_store_memberships (user_id, store_id, role, capabilities)
SELECT u.id, m.store_id, 'manager', ARRAY['reports.submit','reports.view','reports.manage']::TEXT[]
FROM store_memberships m JOIN account_users u ON u.legacy_manager_id = m.manager_user_id;
ALTER TABLE reports ADD COLUMN actor_user_id BIGINT REFERENCES account_users(id);
CREATE INDEX reports_actor_user_idx ON reports (actor_user_id) WHERE actor_user_id IS NOT NULL;

-- MATCH SIMPLE permits a nullable half of a composite FK. Close that gap while
-- allowing operator bootstrap to map a store and its rows in one transaction.
CREATE FUNCTION check_account_store_business_scope() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE checked_store_id BIGINT;
BEGIN
    IF TG_TABLE_NAME = 'stores' THEN
        checked_store_id := NEW.id;
    ELSE
        checked_store_id := NEW.store_id;
    END IF;
    IF EXISTS (
        SELECT 1 FROM account_store_memberships m JOIN stores s ON s.id=m.store_id
        WHERE s.id=checked_store_id AND m.business_id IS DISTINCT FROM s.business_id
    ) OR EXISTS (
        SELECT 1 FROM account_invitations i JOIN stores s ON s.id=i.store_id
        WHERE s.id=checked_store_id AND i.business_id IS DISTINCT FROM s.business_id
    ) THEN
        RAISE EXCEPTION 'Account store business scope does not match the store mapping'
            USING ERRCODE = '23503';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER account_membership_business_scope
AFTER INSERT OR UPDATE ON account_store_memberships DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION check_account_store_business_scope();
CREATE CONSTRAINT TRIGGER account_invitation_business_scope
AFTER INSERT OR UPDATE ON account_invitations DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION check_account_store_business_scope();
CREATE CONSTRAINT TRIGGER account_store_business_scope
AFTER UPDATE OF business_id ON stores DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION check_account_store_business_scope();
