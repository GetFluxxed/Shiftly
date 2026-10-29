-- Company product identities are shared; listings and shelf placements stay local.
CREATE FUNCTION inventory_key(value TEXT) RETURNS TEXT
LANGUAGE SQL IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT lower(btrim(normalize(value, NFKC)))
$$;

CREATE TABLE inventory_products (
    id UUID PRIMARY KEY,
    business_id BIGINT NOT NULL REFERENCES businesses(id),
    sku TEXT NOT NULL CHECK (sku ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$'),
    sku_key TEXT GENERATED ALWAYS AS (inventory_key(sku)) STORED,
    name TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 160),
    base_unit TEXT NOT NULL CHECK (base_unit IN ('each','g','kg','ml','l')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, id),
    UNIQUE (business_id, sku_key)
);
CREATE TABLE inventory_product_skus (
    business_id BIGINT NOT NULL,
    product_id UUID NOT NULL,
    sku TEXT NOT NULL CHECK (sku ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$'),
    sku_key TEXT GENERATED ALWAYS AS (inventory_key(sku)) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (business_id, sku_key),
    UNIQUE (business_id, product_id, sku_key),
    FOREIGN KEY (business_id, product_id) REFERENCES inventory_products(business_id, id)
);
-- Every current SKU is also reserved; former identifiers are never reassigned.
ALTER TABLE inventory_products ADD CONSTRAINT inventory_current_sku_reserved
    FOREIGN KEY (business_id, id, sku_key)
    REFERENCES inventory_product_skus(business_id, product_id, sku_key)
    DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX inventory_products_page_idx ON inventory_products(business_id, active, id);

CREATE TABLE inventory_store_products (
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    product_id UUID NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (business_id, store_id, product_id),
    FOREIGN KEY (store_id, business_id) REFERENCES stores(id, business_id),
    FOREIGN KEY (business_id, product_id) REFERENCES inventory_products(business_id, id)
);
CREATE TABLE inventory_shelves (
    id UUID PRIMARY KEY,
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    name TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 120),
    name_key TEXT GENERATED ALWAYS AS (inventory_key(name)) STORED,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, store_id, id),
    UNIQUE (store_id, name_key),
    FOREIGN KEY (store_id, business_id) REFERENCES stores(id, business_id)
);
CREATE INDEX inventory_shelves_page_idx ON inventory_shelves(store_id, id);
CREATE TABLE inventory_shelf_products (
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    shelf_id UUID NOT NULL,
    product_id UUID NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (store_id, shelf_id, product_id),
    FOREIGN KEY (business_id, store_id, shelf_id) REFERENCES inventory_shelves(business_id, store_id, id),
    FOREIGN KEY (business_id, store_id, product_id) REFERENCES inventory_store_products(business_id, store_id, product_id)
);
CREATE TABLE inventory_changes (
    id BIGSERIAL PRIMARY KEY,
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    actor_user_id BIGINT NOT NULL REFERENCES account_users(id),
    operation TEXT NOT NULL,
    target_id UUID NOT NULL,
    before_value JSONB,
    after_value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (store_id, business_id) REFERENCES stores(id, business_id)
);
CREATE INDEX inventory_changes_scope_idx ON inventory_changes(business_id, target_id, id);
CREATE TABLE inventory_requests (
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    actor_user_id BIGINT NOT NULL REFERENCES account_users(id),
    request_id UUID NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (business_id, store_id, actor_user_id, request_id),
    FOREIGN KEY (store_id, business_id) REFERENCES stores(id, business_id)
);
