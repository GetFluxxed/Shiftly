-- Preserve package label units while inventory arithmetic remains in product base units.
ALTER TABLE inventory_products DROP CONSTRAINT inventory_container_amount_valid;
ALTER TABLE inventory_products ADD CONSTRAINT inventory_container_amount_valid CHECK (
    container_amount IS NULL OR (
        container_amount > 0 AND container_amount <= 999999999.999999999
        AND scale(container_amount) <= 9
        AND (base_unit <> 'each' OR container_amount = trunc(container_amount))
    )
);
ALTER TABLE inventory_products
    ADD COLUMN container_label_amount NUMERIC,
    ADD COLUMN container_label_unit TEXT,
    ADD CONSTRAINT inventory_container_label_pair CHECK (
        (container_label_amount IS NULL) = (container_label_unit IS NULL)
        AND (container_amount IS NOT NULL OR container_label_amount IS NULL)
    ),
    ADD CONSTRAINT inventory_container_label_valid CHECK (
        container_label_amount IS NULL OR (
            container_label_amount > 0 AND container_label_amount <= 999999999.999999999
            AND scale(container_label_amount) <= 9
            AND (container_label_unit <> 'lb' OR scale(container_label_amount) <= 6)
            AND container_label_unit IN ('each','g','kg','lb')
            AND ((base_unit='each')=(container_label_unit='each'))
            AND (container_label_unit <> 'each' OR container_label_amount = trunc(container_label_amount))
        )
    );

ALTER TABLE inventory_packages DROP CONSTRAINT inventory_packages_amount_check;
ALTER TABLE inventory_packages ADD CONSTRAINT inventory_packages_amount_check CHECK (
    amount > 0 AND amount <= 999999999.999999999 AND scale(amount) <= 9
);
ALTER TABLE inventory_packages
    ADD COLUMN label_amount NUMERIC,
    ADD COLUMN label_unit TEXT,
    ADD CONSTRAINT inventory_package_label_pair CHECK ((label_amount IS NULL) = (label_unit IS NULL)),
    ADD CONSTRAINT inventory_package_label_valid CHECK (
        label_amount IS NULL OR (
            label_amount > 0 AND label_amount <= 999999999.999999999
            AND scale(label_amount) <= 9
            AND (label_unit <> 'lb' OR scale(label_amount) <= 6)
            AND label_unit IN ('each','g','kg','lb')
            AND (label_unit <> 'each' OR label_amount = trunc(label_amount))
        )
    ),
    ADD CONSTRAINT inventory_case_has_no_label CHECK (
        contained_package_id IS NULL OR (label_amount IS NULL AND label_unit IS NULL)
    );
