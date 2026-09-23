-- Net contents in one full container, expressed in the product's existing base unit.
-- Unknown sizes stay NULL; upgrading must never invent a package size or stock balance.
ALTER TABLE inventory_products
    ADD COLUMN container_amount NUMERIC,
    ADD CONSTRAINT inventory_container_amount_valid CHECK (
        container_amount IS NULL OR (
            container_amount > 0 AND container_amount <= 999999999.999999
            AND scale(container_amount) <= 6
            AND (base_unit <> 'each' OR container_amount = trunc(container_amount))
        )
    ),
    ADD COLUMN name_sort TEXT COLLATE "C"
        GENERATED ALWAYS AS (inventory_key(name)) STORED;
CREATE INDEX inventory_products_name_page_idx
    ON inventory_products(business_id, name_sort, id);
