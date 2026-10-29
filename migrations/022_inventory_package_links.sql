-- Preserve duplicate catalog identities while explicitly redirecting them to one
-- canonical product/package. Existing aliases and historical foreign keys remain.
ALTER TABLE inventory_products ADD COLUMN canonical_product_id UUID;
ALTER TABLE inventory_products ADD CONSTRAINT inventory_product_canonical_not_self
    CHECK (canonical_product_id IS NULL OR canonical_product_id <> id);
ALTER TABLE inventory_products ADD CONSTRAINT inventory_product_canonical_same_business
    FOREIGN KEY (business_id,canonical_product_id)
    REFERENCES inventory_products(business_id,id);
CREATE INDEX inventory_products_canonical
    ON inventory_products(business_id,canonical_product_id)
    WHERE canonical_product_id IS NOT NULL;

ALTER TABLE inventory_packages ADD CONSTRAINT inventory_packages_business_id_id_unique
    UNIQUE (business_id,id);
ALTER TABLE inventory_packages ADD COLUMN redirect_package_id UUID;
ALTER TABLE inventory_packages ADD CONSTRAINT inventory_package_redirect_not_self
    CHECK (redirect_package_id IS NULL OR redirect_package_id <> id);
ALTER TABLE inventory_packages ADD CONSTRAINT inventory_package_redirect_same_business
    FOREIGN KEY (business_id,redirect_package_id)
    REFERENCES inventory_packages(business_id,id);
CREATE INDEX inventory_packages_redirect
    ON inventory_packages(business_id,redirect_package_id)
    WHERE redirect_package_id IS NOT NULL;

