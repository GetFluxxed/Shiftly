-- Keep original hashes and historical records while isolating duplicate checks.
ALTER TABLE reports
    ADD CONSTRAINT reports_store_report_hash_key UNIQUE (store_id, report_hash);

-- Legacy reports without a store retain their existing duplicate protection.
CREATE UNIQUE INDEX reports_legacy_report_hash_idx
    ON reports (report_hash) WHERE store_id IS NULL;

ALTER TABLE reports DROP CONSTRAINT reports_report_hash_key;
