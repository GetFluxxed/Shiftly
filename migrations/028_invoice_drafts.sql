-- Reviewed invoice drafts provide incoming previews without posting stock.
CREATE TABLE inventory_invoice_drafts (
    id UUID PRIMARY KEY,
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    supplier TEXT NOT NULL DEFAULT '' CHECK (char_length(supplier) <= 120),
    invoice_number TEXT NOT NULL DEFAULT '' CHECK (char_length(invoice_number) <= 80),
    state TEXT NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','closed')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    baseline_count_id UUID REFERENCES inventory_counts(id),
    created_by BIGINT NOT NULL REFERENCES account_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_by BIGINT REFERENCES account_users(id),
    closed_at TIMESTAMPTZ,
    UNIQUE (business_id,store_id,id),
    FOREIGN KEY (store_id,business_id) REFERENCES stores(id,business_id),
    CHECK ((state='closed') = (closed_by IS NOT NULL AND closed_at IS NOT NULL))
);
CREATE UNIQUE INDEX inventory_invoice_active_number
    ON inventory_invoice_drafts(store_id,lower(supplier),lower(invoice_number))
    WHERE state='draft' AND supplier<>'' AND invoice_number<>'';
CREATE INDEX inventory_invoice_history
    ON inventory_invoice_drafts(store_id,updated_at DESC,id DESC);

CREATE TABLE inventory_invoice_lines (
    id UUID PRIMARY KEY,
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    invoice_id UUID NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0 AND position < 60),
    description TEXT NOT NULL CHECK (char_length(btrim(description)) BETWEEN 1 AND 160),
    sku TEXT NOT NULL DEFAULT '' CHECK (char_length(sku) <= 64),
    product_id UUID,
    package_id UUID,
    quantity NUMERIC CHECK (quantity >= 0 AND quantity <= 999999999999999.999999999 AND scale(quantity) <= 9),
    unit TEXT NOT NULL DEFAULT '' CHECK (unit IN ('','kg','g','lb','each','package')),
    received BOOLEAN NOT NULL DEFAULT FALSE,
    product_name TEXT,
    base_unit TEXT CHECK (base_unit IN ('each','g','kg')),
    normalized_quantity NUMERIC CHECK (normalized_quantity > 0 AND normalized_quantity <= 999999999999999.999999999 AND scale(normalized_quantity) <= 9),
    package_name TEXT,
    package_amount NUMERIC,
    product_version INTEGER,
    package_version INTEGER,
    UNIQUE (invoice_id,position),
    UNIQUE (business_id,store_id,invoice_id,id),
    FOREIGN KEY (business_id,store_id,invoice_id) REFERENCES inventory_invoice_drafts(business_id,store_id,id),
    FOREIGN KEY (business_id,product_id) REFERENCES inventory_products(business_id,id),
    FOREIGN KEY (business_id,package_id) REFERENCES inventory_packages(business_id,id),
    CHECK ((product_id IS NULL) = (product_name IS NULL)),
    CHECK ((product_id IS NULL) = (base_unit IS NULL)),
    CHECK ((product_id IS NULL) = (normalized_quantity IS NULL)),
    CHECK ((product_id IS NULL) = (product_version IS NULL)),
    CHECK (product_id IS NULL OR (quantity IS NOT NULL AND quantity > 0 AND unit<>'')),
    CHECK ((package_id IS NULL) = (package_name IS NULL)),
    CHECK ((package_id IS NULL) = (package_amount IS NULL)),
    CHECK ((package_id IS NULL) = (package_version IS NULL)),
    CHECK ((package_id IS NULL) = (unit<>'package'))
);
CREATE INDEX inventory_invoice_lines_product
    ON inventory_invoice_lines(store_id,product_id) WHERE product_id IS NOT NULL;

CREATE FUNCTION inventory_invoice_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE invoice_state TEXT;
BEGIN
    IF TG_TABLE_NAME='inventory_invoice_drafts' THEN
        IF TG_OP='DELETE' OR OLD.state='closed' THEN
            RAISE EXCEPTION 'Closed invoice history cannot be rewritten' USING ERRCODE='23514';
        END IF;
        IF ROW(OLD.id,OLD.business_id,OLD.store_id,OLD.created_by,OLD.created_at)
            IS DISTINCT FROM ROW(NEW.id,NEW.business_id,NEW.store_id,NEW.created_by,NEW.created_at) THEN
            RAISE EXCEPTION 'Invoice identity cannot change' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
    END IF;
    SELECT state INTO invoice_state FROM inventory_invoice_drafts
    WHERE id=CASE WHEN TG_OP='DELETE' THEN OLD.invoice_id ELSE NEW.invoice_id END FOR SHARE;
    IF invoice_state<>'draft' THEN
        RAISE EXCEPTION 'Closed invoice lines cannot be rewritten' USING ERRCODE='23514';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER inventory_invoice_drafts_guard BEFORE UPDATE OR DELETE ON inventory_invoice_drafts
    FOR EACH ROW EXECUTE FUNCTION inventory_invoice_guard();
CREATE TRIGGER inventory_invoice_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON inventory_invoice_lines
    FOR EACH ROW EXECUTE FUNCTION inventory_invoice_guard();
