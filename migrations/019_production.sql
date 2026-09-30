CREATE TABLE production_recipes (
    id UUID PRIMARY KEY,
    business_id BIGINT NOT NULL REFERENCES businesses(id),
    current_revision_id UUID,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_by BIGINT NOT NULL REFERENCES account_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id,id)
);

CREATE TABLE production_recipe_revisions (
    id UUID PRIMARY KEY,
    business_id BIGINT NOT NULL,
    recipe_id UUID NOT NULL,
    revision_number INTEGER NOT NULL CHECK (revision_number > 0),
    name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 160),
    yield_amount NUMERIC NOT NULL CHECK (yield_amount > 0 AND scale(yield_amount)<=9),
    yield_unit TEXT NOT NULL CHECK (char_length(btrim(yield_unit)) BETWEEN 1 AND 40),
    instructions TEXT NOT NULL DEFAULT '',
    sealed BOOLEAN NOT NULL DEFAULT FALSE,
    created_by BIGINT NOT NULL REFERENCES account_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id,recipe_id,id),
    UNIQUE (recipe_id,id),
    UNIQUE (recipe_id,revision_number),
    FOREIGN KEY (business_id,recipe_id) REFERENCES production_recipes(business_id,id)
);
ALTER TABLE production_recipes ADD CONSTRAINT production_current_revision
    FOREIGN KEY (business_id,id,current_revision_id)
    REFERENCES production_recipe_revisions(business_id,recipe_id,id)
    DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX production_recipe_page ON production_recipes(business_id,id);

CREATE TABLE production_recipe_ingredients (
    business_id BIGINT NOT NULL,
    recipe_id UUID NOT NULL,
    revision_id UUID NOT NULL,
    product_id UUID NOT NULL,
    name TEXT NOT NULL,
    sku TEXT NOT NULL,
    amount NUMERIC NOT NULL CHECK (amount > 0 AND scale(amount)<=9),
    unit TEXT NOT NULL CHECK (unit IN ('each','g','kg')),
    base_unit TEXT NOT NULL CHECK (base_unit IN ('each','g','kg')),
    base_amount NUMERIC NOT NULL CHECK (base_amount > 0 AND scale(base_amount)<=9),
    PRIMARY KEY (revision_id,product_id),
    FOREIGN KEY (business_id,recipe_id,revision_id) REFERENCES production_recipe_revisions(business_id,recipe_id,id),
    FOREIGN KEY (business_id,product_id) REFERENCES inventory_products(business_id,id)
);

CREATE TABLE production_logs (
    id UUID PRIMARY KEY,
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    business_date DATE NOT NULL,
    state TEXT NOT NULL DEFAULT 'building' CHECK (state IN ('building','confirmed','reversed')),
    payload_fingerprint CHAR(64) NOT NULL,
    created_by BIGINT NOT NULL REFERENCES account_users(id),
    creator_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reversed_by BIGINT REFERENCES account_users(id),
    reversed_at TIMESTAMPTZ,
    reversal_reason TEXT,
    UNIQUE (business_id,store_id,id),
    FOREIGN KEY (store_id,business_id) REFERENCES stores(id,business_id),
    CHECK ((state='reversed')=(reversed_by IS NOT NULL AND reversed_at IS NOT NULL AND reversal_reason IS NOT NULL))
);
CREATE INDEX production_log_history ON production_logs(store_id,created_at DESC,id DESC);

CREATE TABLE production_log_entries (
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    log_id UUID NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    recipe_id UUID NOT NULL,
    revision_id UUID NOT NULL,
    name TEXT NOT NULL,
    yield_amount NUMERIC NOT NULL CHECK (yield_amount > 0 AND scale(yield_amount)<=9),
    yield_unit TEXT NOT NULL CHECK (char_length(btrim(yield_unit)) BETWEEN 1 AND 40),
    batches INTEGER NOT NULL CHECK (batches BETWEEN 1 AND 1000),
    PRIMARY KEY (log_id,sequence),
    FOREIGN KEY (business_id,store_id,log_id) REFERENCES production_logs(business_id,store_id,id),
    FOREIGN KEY (business_id,recipe_id,revision_id) REFERENCES production_recipe_revisions(business_id,recipe_id,id)
);

CREATE TABLE production_log_ingredients (
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    log_id UUID NOT NULL,
    product_id UUID NOT NULL,
    name TEXT NOT NULL,
    sku TEXT NOT NULL,
    base_unit TEXT NOT NULL CHECK (base_unit IN ('each','g','kg')),
    recipe_amount NUMERIC NOT NULL CHECK (recipe_amount > 0 AND scale(recipe_amount)<=9),
    allowance_amount NUMERIC NOT NULL CHECK (allowance_amount > 0 AND scale(allowance_amount)<=9),
    quantity NUMERIC NOT NULL CHECK (quantity=recipe_amount+allowance_amount AND scale(quantity)<=9),
    balance_before NUMERIC NOT NULL CHECK (balance_before >= quantity AND scale(balance_before)<=9),
    balance_after NUMERIC NOT NULL CHECK (balance_after=balance_before-quantity AND scale(balance_after)<=9),
    count_id UUID NOT NULL,
    movement_id UUID NOT NULL UNIQUE,
    PRIMARY KEY (log_id,product_id),
    FOREIGN KEY (business_id,store_id,log_id) REFERENCES production_logs(business_id,store_id,id),
    FOREIGN KEY (business_id,product_id) REFERENCES inventory_products(business_id,id),
    FOREIGN KEY (business_id,store_id,count_id) REFERENCES inventory_counts(business_id,store_id,id),
    FOREIGN KEY (business_id,store_id,product_id,movement_id)
      REFERENCES inventory_stock_movements(business_id,store_id,product_id,id)
);

CREATE TABLE production_requests (
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    request_id UUID NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (business_id,store_id,request_id),
    FOREIGN KEY (store_id,business_id) REFERENCES stores(id,business_id)
);

CREATE FUNCTION production_immutable_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Production history cannot be deleted' USING ERRCODE='23514'; END IF;
    IF TG_TABLE_NAME IN ('production_recipe_ingredients','production_log_entries','production_log_ingredients','production_requests') THEN
        RAISE EXCEPTION 'Production evidence cannot be rewritten' USING ERRCODE='23514';
    END IF;
    IF TG_TABLE_NAME='production_logs' AND NOT (
       (OLD.state='building' AND NEW.state='confirmed' AND NEW.reversed_by IS NULL AND NEW.reversed_at IS NULL AND NEW.reversal_reason IS NULL)
       OR (OLD.state='confirmed' AND NEW.state='reversed')
       ) THEN
        RAISE EXCEPTION 'Production log transition is not permitted' USING ERRCODE='23514';
    END IF;
    IF TG_TABLE_NAME='production_logs' AND
       ROW(OLD.id,OLD.business_id,OLD.store_id,OLD.business_date,OLD.payload_fingerprint,OLD.created_by,OLD.creator_name,OLD.created_at)
          IS DISTINCT FROM ROW(NEW.id,NEW.business_id,NEW.store_id,NEW.business_date,NEW.payload_fingerprint,NEW.created_by,NEW.creator_name,NEW.created_at) THEN
        RAISE EXCEPTION 'Only a confirmed production log may be reversed' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE FUNCTION production_recipe_revision_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='UPDATE' AND NOT OLD.sealed AND NEW.sealed
       AND ROW(OLD.id,OLD.business_id,OLD.recipe_id,OLD.revision_number,OLD.name,OLD.yield_amount,OLD.yield_unit,OLD.instructions,OLD.created_by,OLD.created_at)
          IS NOT DISTINCT FROM ROW(NEW.id,NEW.business_id,NEW.recipe_id,NEW.revision_number,NEW.name,NEW.yield_amount,NEW.yield_unit,NEW.instructions,NEW.created_by,NEW.created_at) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'Recipe revision evidence cannot be rewritten' USING ERRCODE='23514';
END $$;
CREATE FUNCTION production_insert_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE parent_state TEXT; revision_sealed BOOLEAN;
BEGIN
    IF TG_TABLE_NAME='production_recipe_ingredients' THEN
        SELECT sealed INTO revision_sealed FROM production_recipe_revisions WHERE id=NEW.revision_id FOR SHARE;
        IF revision_sealed THEN RAISE EXCEPTION 'A sealed recipe revision cannot receive ingredients' USING ERRCODE='23514'; END IF;
    ELSE
        SELECT state INTO parent_state FROM production_logs WHERE id=NEW.log_id FOR SHARE;
        IF parent_state<>'building' THEN RAISE EXCEPTION 'A completed production log cannot receive evidence' USING ERRCODE='23514'; END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER production_recipe_revisions_guard BEFORE UPDATE OR DELETE ON production_recipe_revisions FOR EACH ROW EXECUTE FUNCTION production_recipe_revision_guard();
CREATE TRIGGER production_recipe_ingredients_guard BEFORE UPDATE OR DELETE ON production_recipe_ingredients FOR EACH ROW EXECUTE FUNCTION production_immutable_guard();
CREATE TRIGGER production_logs_guard BEFORE UPDATE OR DELETE ON production_logs FOR EACH ROW EXECUTE FUNCTION production_immutable_guard();
CREATE TRIGGER production_log_entries_guard BEFORE UPDATE OR DELETE ON production_log_entries FOR EACH ROW EXECUTE FUNCTION production_immutable_guard();
CREATE TRIGGER production_log_ingredients_guard BEFORE UPDATE OR DELETE ON production_log_ingredients FOR EACH ROW EXECUTE FUNCTION production_immutable_guard();
CREATE TRIGGER production_requests_guard BEFORE UPDATE OR DELETE ON production_requests FOR EACH ROW EXECUTE FUNCTION production_immutable_guard();
CREATE TRIGGER production_recipe_ingredients_insert_guard BEFORE INSERT ON production_recipe_ingredients FOR EACH ROW EXECUTE FUNCTION production_insert_guard();
CREATE TRIGGER production_log_entries_insert_guard BEFORE INSERT ON production_log_entries FOR EACH ROW EXECUTE FUNCTION production_insert_guard();
CREATE TRIGGER production_log_ingredients_insert_guard BEFORE INSERT ON production_log_ingredients FOR EACH ROW EXECUTE FUNCTION production_insert_guard();
