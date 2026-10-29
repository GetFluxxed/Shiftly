-- Draft counts may append newly active catalog products without rewriting captured evidence.
DROP TRIGGER inventory_counts_guard ON inventory_counts;

CREATE FUNCTION inventory_counts_expansion_guard() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' OR OLD.state IN ('posted','cancelled') THEN
        RAISE EXCEPTION 'Completed count history cannot be rewritten' USING ERRCODE='23514';
    END IF;
    IF ROW(OLD.id,OLD.business_id,OLD.store_id,OLD.business_date,OLD.started_by,OLD.started_at)
        IS DISTINCT FROM ROW(NEW.id,NEW.business_id,NEW.store_id,NEW.business_date,NEW.started_by,NEW.started_at) THEN
        RAISE EXCEPTION 'Count identity cannot change' USING ERRCODE='23514';
    END IF;
    IF OLD.configuration_hash IS DISTINCT FROM NEW.configuration_hash
        AND NOT (OLD.state='draft' AND NEW.state='draft' AND NEW.version=OLD.version+1) THEN
        RAISE EXCEPTION 'Only draft catalog expansion can update count configuration' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER inventory_counts_guard BEFORE UPDATE OR DELETE ON inventory_counts
FOR EACH ROW EXECUTE FUNCTION inventory_counts_expansion_guard();
