-- Recipe-only ingredients preserve recipe fidelity without creating stock identities.
ALTER TABLE production_recipe_revisions
    ADD COLUMN reference_ingredients JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD CONSTRAINT production_reference_ingredients_array
        CHECK (jsonb_typeof(reference_ingredients)='array'),
    ADD CONSTRAINT production_reference_ingredients_limit
        CHECK (jsonb_array_length(reference_ingredients)<=50);

CREATE OR REPLACE FUNCTION production_recipe_revision_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='UPDATE' AND NOT OLD.sealed AND NEW.sealed
       AND ROW(OLD.id,OLD.business_id,OLD.recipe_id,OLD.revision_number,OLD.name,OLD.yield_amount,OLD.yield_unit,OLD.instructions,OLD.reference_ingredients,OLD.created_by,OLD.created_at)
          IS NOT DISTINCT FROM ROW(NEW.id,NEW.business_id,NEW.recipe_id,NEW.revision_number,NEW.name,NEW.yield_amount,NEW.yield_unit,NEW.instructions,NEW.reference_ingredients,NEW.created_by,NEW.created_at) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'Recipe revision evidence cannot be rewritten' USING ERRCODE='23514';
END $$;
