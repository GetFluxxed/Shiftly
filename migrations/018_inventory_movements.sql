-- Physical verification and running stock have separate provenance.
-- Existing count evidence stays immutable; only new snapshot metadata is filled.
CREATE TABLE inventory_stock_movements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    product_id UUID NOT NULL,
    base_unit TEXT NOT NULL CHECK (base_unit IN ('each','g','kg')),
    kind TEXT NOT NULL CHECK (kind IN ('opening','count','production','reversal')),
    source_id UUID NOT NULL,
    quantity_before NUMERIC CHECK (quantity_before >= 0 AND quantity_before <= 999999999999999.999999999 AND scale(quantity_before)<=9),
    quantity_after NUMERIC NOT NULL CHECK (quantity_after >= 0 AND quantity_after <= 999999999999999.999999999 AND scale(quantity_after)<=9),
    delta NUMERIC GENERATED ALWAYS AS (quantity_after-COALESCE(quantity_before,0)) STORED,
    version BIGINT NOT NULL CHECK (version>0),
    reverses_id UUID UNIQUE REFERENCES inventory_stock_movements(id),
    actor_user_id BIGINT NOT NULL REFERENCES account_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id,store_id,product_id,id),
    UNIQUE (business_id,store_id,product_id,version),
    UNIQUE (store_id,kind,source_id,product_id),
    FOREIGN KEY (business_id,store_id,product_id) REFERENCES inventory_store_products(business_id,store_id,product_id),
    CHECK ((kind='opening') = (quantity_before IS NULL)),
    CHECK ((kind='reversal') = (reverses_id IS NOT NULL)),
    CHECK (kind<>'production' OR quantity_after<quantity_before)
);
CREATE INDEX inventory_movements_history ON inventory_stock_movements(store_id,created_at DESC,id DESC);
-- Use count lineage rather than wall-clock order (timestamps may tie).
WITH RECURSIVE history AS (
    SELECT p.business_id,p.store_id,p.product_id,c.base_unit,p.count_id,
           p.quantity_before,p.quantity_after,p.posted_by,p.posted_at,1::bigint AS version
    FROM inventory_stock_postings p JOIN inventory_count_products c ON c.count_id=p.count_id AND c.product_id=p.product_id
    WHERE c.previous_count_id IS NULL
    UNION ALL
    SELECT p.business_id,p.store_id,p.product_id,c.base_unit,p.count_id,
           p.quantity_before,p.quantity_after,p.posted_by,p.posted_at,h.version+1
    FROM history h JOIN inventory_count_products c ON c.store_id=h.store_id AND c.product_id=h.product_id AND c.previous_count_id=h.count_id
    JOIN inventory_stock_postings p ON p.count_id=c.count_id AND p.product_id=c.product_id
)
INSERT INTO inventory_stock_movements(business_id,store_id,product_id,base_unit,kind,source_id,
    quantity_before,quantity_after,version,actor_user_id,created_at)
SELECT business_id,store_id,product_id,base_unit,
       CASE WHEN quantity_before IS NULL THEN 'opening' ELSE 'count' END,count_id,
       quantity_before,quantity_after,version,posted_by,posted_at FROM history;

ALTER TABLE inventory_stock_balances ADD COLUMN version BIGINT,
    ADD COLUMN last_movement_id UUID, ADD COLUMN last_counted_at TIMESTAMPTZ;
UPDATE inventory_stock_balances b SET version=m.version,last_movement_id=m.id,last_counted_at=m.created_at
FROM inventory_stock_movements m WHERE m.store_id=b.store_id AND m.product_id=b.product_id AND m.source_id=b.count_id;
ALTER TABLE inventory_stock_balances ALTER COLUMN version SET NOT NULL,
    ALTER COLUMN last_movement_id SET NOT NULL, ALTER COLUMN last_counted_at SET NOT NULL,
    ADD CONSTRAINT inventory_balance_version_positive CHECK (version>0),
    ADD CONSTRAINT inventory_balance_movement FOREIGN KEY (business_id,store_id,product_id,last_movement_id)
        REFERENCES inventory_stock_movements(business_id,store_id,product_id,id);
COMMENT ON COLUMN inventory_stock_balances.count_id IS 'Last physical count, not necessarily the latest stock movement';
COMMENT ON COLUMN inventory_stock_balances.counted_on IS 'Business date of last physical count';

ALTER TABLE inventory_count_products ADD COLUMN previous_stock_version BIGINT;
ALTER TABLE inventory_count_products DISABLE TRIGGER inventory_count_products_guard;
UPDATE inventory_count_products c SET previous_stock_version=m.version
FROM inventory_stock_movements m WHERE m.store_id=c.store_id AND m.product_id=c.product_id AND m.source_id=c.previous_count_id;
ALTER TABLE inventory_count_products ENABLE TRIGGER inventory_count_products_guard;
ALTER TABLE inventory_count_products ADD CONSTRAINT inventory_count_baseline_version
    CHECK ((previous_stock_version IS NULL)=(previous_quantity IS NULL) AND (previous_stock_version IS NULL OR previous_stock_version>0));

CREATE FUNCTION inventory_movement_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Stock movement history cannot be rewritten' USING ERRCODE='23514';
END $$;
CREATE TRIGGER inventory_movements_immutable BEFORE UPDATE OR DELETE ON inventory_stock_movements
    FOR EACH ROW EXECUTE FUNCTION inventory_movement_guard();
