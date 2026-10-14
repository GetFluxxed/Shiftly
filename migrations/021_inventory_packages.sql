-- Named full-package options share one canonical product and exact base-unit amount.
CREATE TABLE inventory_packages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id BIGINT NOT NULL,
    product_id UUID NOT NULL,
    name TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 120),
    name_key TEXT GENERATED ALWAYS AS (inventory_key(name)) STORED,
    amount NUMERIC NOT NULL CHECK (
        amount > 0 AND amount <= 999999999.999999
        AND scale(amount) <= 6
    ),
    kind TEXT NOT NULL CHECK (kind IN ('container','box','case')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    contained_package_id UUID,
    contained_count INTEGER,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, product_id, id),
    UNIQUE (business_id, product_id, name_key),
    FOREIGN KEY (business_id, product_id) REFERENCES inventory_products(business_id, id),
    CHECK ((contained_package_id IS NULL) = (contained_count IS NULL)),
    CHECK (contained_count IS NULL OR (kind='case' AND contained_count > 0 AND contained_count <= 1000000)),
    CHECK (contained_package_id IS NULL OR contained_package_id <> id)
);
ALTER TABLE inventory_packages ADD CONSTRAINT inventory_package_contained_same_product
    FOREIGN KEY (business_id, product_id, contained_package_id)
    REFERENCES inventory_packages(business_id, product_id, id);
CREATE UNIQUE INDEX inventory_packages_one_default
    ON inventory_packages(business_id, product_id) WHERE is_default;
CREATE INDEX inventory_packages_product ON inventory_packages(business_id, product_id, id);

CREATE FUNCTION inventory_package_integrity_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE product_unit TEXT; child inventory_packages%ROWTYPE;
BEGIN
    SELECT base_unit INTO product_unit FROM inventory_products
    WHERE business_id=NEW.business_id AND id=NEW.product_id;
    IF product_unit='each' AND NEW.amount <> trunc(NEW.amount) THEN
        RAISE EXCEPTION 'Item package amounts must be whole numbers' USING ERRCODE='23514';
    END IF;
    IF NEW.contained_package_id IS NOT NULL THEN
        SELECT * INTO child FROM inventory_packages
        WHERE business_id=NEW.business_id AND product_id=NEW.product_id
          AND id=NEW.contained_package_id;
        IF NOT FOUND OR child.contained_package_id IS NOT NULL THEN
            RAISE EXCEPTION 'A case must reference a leaf package of the same product' USING ERRCODE='23514';
        END IF;
        IF NEW.active AND (NOT child.active OR NEW.amount <> child.amount * NEW.contained_count) THEN
            RAISE EXCEPTION 'An active case conversion must match an active leaf package' USING ERRCODE='23514';
        END IF;
    END IF;
    IF TG_OP='UPDATE' AND NEW.amount IS DISTINCT FROM OLD.amount AND EXISTS (
        SELECT 1 FROM inventory_packages dependent
        WHERE dependent.business_id=OLD.business_id AND dependent.product_id=OLD.product_id
          AND dependent.contained_package_id=OLD.id AND dependent.active
    ) THEN
        RAISE EXCEPTION 'Active dependent cases must be archived first' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER inventory_package_integrity BEFORE INSERT OR UPDATE ON inventory_packages
    FOR EACH ROW EXECUTE FUNCTION inventory_package_integrity_guard();

-- Prevent direct SQL from exceeding the bounded package catalog.
CREATE FUNCTION inventory_package_limit_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(NEW.business_id::text || ':' || NEW.product_id::text, 0));
    IF (SELECT count(*) FROM inventory_packages
        WHERE business_id=NEW.business_id AND product_id=NEW.product_id) >= 40 THEN
        RAISE EXCEPTION 'A product cannot have more than 40 packages' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER inventory_package_limit BEFORE INSERT ON inventory_packages
    FOR EACH ROW EXECUTE FUNCTION inventory_package_limit_guard();

INSERT INTO inventory_packages(business_id,product_id,name,amount,kind,is_default)
SELECT business_id,id,'Container',container_amount,'container',TRUE
FROM inventory_products WHERE container_amount IS NOT NULL;

ALTER TABLE inventory_product_skus ADD COLUMN package_id UUID;
ALTER TABLE inventory_product_skus ADD CONSTRAINT inventory_product_sku_package
    FOREIGN KEY (business_id,product_id,package_id)
    REFERENCES inventory_packages(business_id,product_id,id);
UPDATE inventory_product_skus s SET package_id=p.id
FROM inventory_packages p
WHERE p.business_id=s.business_id AND p.product_id=s.product_id AND p.is_default;

-- Existing count snapshots remain byte-for-byte meaningful; only future counts populate this.
ALTER TABLE inventory_count_products
    ADD COLUMN packages JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD CONSTRAINT inventory_count_packages_array CHECK (jsonb_typeof(packages)='array');
