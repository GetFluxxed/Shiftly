-- A recipe may use the same product in its base and variegato topping.
ALTER TABLE production_recipe_ingredients
    ADD COLUMN section TEXT NOT NULL DEFAULT 'base'
        CHECK (section IN ('base','variegato'));

ALTER TABLE production_recipe_ingredients
    DROP CONSTRAINT production_recipe_ingredients_pkey,
    ADD PRIMARY KEY (revision_id,product_id,section);
