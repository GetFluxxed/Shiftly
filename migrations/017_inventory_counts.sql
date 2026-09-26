-- Count observations are independent of catalog/layout configuration.
CREATE TABLE inventory_counts (
    id UUID PRIMARY KEY,
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    business_date DATE NOT NULL,
    state TEXT NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','review','posted','cancelled')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    configuration_hash CHAR(64) NOT NULL,
    started_by BIGINT NOT NULL REFERENCES account_users(id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_by BIGINT REFERENCES account_users(id),
    reviewed_at TIMESTAMPTZ,
    posted_by BIGINT REFERENCES account_users(id),
    posted_at TIMESTAMPTZ,
    UNIQUE (business_id,store_id,id),
    FOREIGN KEY (store_id,business_id) REFERENCES stores(id,business_id),
    CHECK ((state='posted') = (posted_at IS NOT NULL AND posted_by IS NOT NULL))
);
CREATE UNIQUE INDEX inventory_one_open_count ON inventory_counts(store_id) WHERE state IN ('draft','review');
CREATE INDEX inventory_counts_history ON inventory_counts(store_id,started_at DESC,id DESC);

CREATE TABLE inventory_count_products (
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    count_id UUID NOT NULL,
    product_id UUID NOT NULL,
    name TEXT NOT NULL,
    sku TEXT NOT NULL,
    base_unit TEXT NOT NULL CHECK (base_unit IN ('each','g','kg')),
    container_amount NUMERIC,
    product_version INTEGER NOT NULL CHECK (product_version > 0),
    previous_quantity NUMERIC CHECK (previous_quantity >= 0 AND previous_quantity <= 999999999999999.999999999 AND scale(previous_quantity)<=9),
    previous_count_id UUID,
    PRIMARY KEY (count_id,product_id),
    UNIQUE (business_id,store_id,count_id,product_id),
    FOREIGN KEY (business_id,store_id,count_id) REFERENCES inventory_counts(business_id,store_id,id),
    FOREIGN KEY (business_id,store_id,product_id) REFERENCES inventory_store_products(business_id,store_id,product_id),
    FOREIGN KEY (business_id,store_id,previous_count_id) REFERENCES inventory_counts(business_id,store_id,id),
    CHECK ((previous_quantity IS NULL) = (previous_count_id IS NULL))
);
CREATE TABLE inventory_count_lines (
    id UUID PRIMARY KEY,
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    count_id UUID NOT NULL,
    product_id UUID NOT NULL,
    shelf_id UUID,
    shelf_name TEXT NOT NULL,
    quantity NUMERIC CHECK (quantity >= 0 AND quantity <= 999999999999999.999999999 AND scale(quantity)<=9),
    entry JSONB,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    observed_by BIGINT REFERENCES account_users(id),
    observed_at TIMESTAMPTZ,
    UNIQUE NULLS NOT DISTINCT (count_id,product_id,shelf_id),
    FOREIGN KEY (business_id,store_id,count_id,product_id) REFERENCES inventory_count_products(business_id,store_id,count_id,product_id),
    FOREIGN KEY (business_id,store_id,shelf_id) REFERENCES inventory_shelves(business_id,store_id,id),
    CHECK ((quantity IS NULL AND entry IS NULL AND observed_by IS NULL AND observed_at IS NULL)
        OR (quantity IS NOT NULL AND entry IS NOT NULL AND observed_by IS NOT NULL AND observed_at IS NOT NULL))
);
CREATE INDEX inventory_count_lines_page ON inventory_count_lines(count_id,id);

CREATE TABLE inventory_stock_postings (
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    count_id UUID NOT NULL,
    product_id UUID NOT NULL,
    quantity_before NUMERIC,
    quantity_after NUMERIC NOT NULL CHECK (quantity_after >= 0 AND quantity_after <= 999999999999999.999999999 AND scale(quantity_after)<=9),
    difference NUMERIC GENERATED ALWAYS AS (quantity_after-quantity_before) STORED,
    posted_by BIGINT NOT NULL REFERENCES account_users(id),
    posted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (count_id,product_id),
    UNIQUE (business_id,store_id,count_id,product_id),
    FOREIGN KEY (business_id,store_id,count_id,product_id) REFERENCES inventory_count_products(business_id,store_id,count_id,product_id)
);
CREATE TABLE inventory_stock_balances (
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    product_id UUID NOT NULL,
    count_id UUID NOT NULL,
    quantity NUMERIC NOT NULL CHECK (quantity >= 0 AND quantity <= 999999999999999.999999999 AND scale(quantity)<=9),
    base_unit TEXT NOT NULL CHECK (base_unit IN ('each','g','kg')),
    counted_on DATE NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (business_id,store_id,product_id),
    FOREIGN KEY (business_id,store_id,count_id,product_id) REFERENCES inventory_stock_postings(business_id,store_id,count_id,product_id)
);

CREATE FUNCTION inventory_count_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE count_state TEXT;
BEGIN
    IF TG_TABLE_NAME='inventory_counts' THEN
        IF TG_OP='DELETE' OR OLD.state IN ('posted','cancelled') THEN
            RAISE EXCEPTION 'Completed count history cannot be rewritten' USING ERRCODE='23514';
        END IF;
        IF ROW(OLD.id,OLD.business_id,OLD.store_id,OLD.business_date,OLD.configuration_hash,OLD.started_by,OLD.started_at)
            IS DISTINCT FROM ROW(NEW.id,NEW.business_id,NEW.store_id,NEW.business_date,NEW.configuration_hash,NEW.started_by,NEW.started_at) THEN
            RAISE EXCEPTION 'Count identity and snapshot cannot change' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP='DELETE' OR (TG_TABLE_NAME IN ('inventory_count_products','inventory_stock_postings') AND TG_OP='UPDATE') THEN
        RAISE EXCEPTION 'Count evidence cannot be rewritten' USING ERRCODE='23514';
    END IF;
    SELECT state INTO count_state FROM inventory_counts WHERE id=NEW.count_id FOR SHARE;
    IF (TG_TABLE_NAME='inventory_stock_postings' AND count_state <> 'review')
        OR (TG_TABLE_NAME <> 'inventory_stock_postings' AND count_state <> 'draft') THEN
        RAISE EXCEPTION 'Count state does not permit this change' USING ERRCODE='23514';
    END IF;
    IF TG_TABLE_NAME='inventory_count_lines' AND TG_OP='UPDATE' THEN
        IF ROW(OLD.id,OLD.business_id,OLD.store_id,OLD.count_id,OLD.product_id,OLD.shelf_id,OLD.shelf_name)
            IS DISTINCT FROM ROW(NEW.id,NEW.business_id,NEW.store_id,NEW.count_id,NEW.product_id,NEW.shelf_id,NEW.shelf_name) THEN
            RAISE EXCEPTION 'Count location cannot change' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER inventory_counts_guard BEFORE UPDATE OR DELETE ON inventory_counts FOR EACH ROW EXECUTE FUNCTION inventory_count_guard();
CREATE TRIGGER inventory_count_products_guard BEFORE INSERT OR UPDATE OR DELETE ON inventory_count_products FOR EACH ROW EXECUTE FUNCTION inventory_count_guard();
CREATE TRIGGER inventory_count_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON inventory_count_lines FOR EACH ROW EXECUTE FUNCTION inventory_count_guard();
CREATE TRIGGER inventory_stock_postings_guard BEFORE INSERT OR UPDATE OR DELETE ON inventory_stock_postings FOR EACH ROW EXECUTE FUNCTION inventory_count_guard();
