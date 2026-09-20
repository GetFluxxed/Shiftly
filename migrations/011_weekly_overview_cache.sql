CREATE TABLE IF NOT EXISTS weekly_overview_cache (
    store_id BIGINT PRIMARY KEY REFERENCES stores(id) ON DELETE CASCADE,
    source_fingerprint CHAR(64) NOT NULL,
    report_count INTEGER NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    wins TEXT[] NOT NULL DEFAULT '{}',
    risks TEXT[] NOT NULL DEFAULT '{}',
    follow_up TEXT NOT NULL DEFAULT '',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
