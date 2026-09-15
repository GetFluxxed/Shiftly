CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY,
    employee TEXT NOT NULL CHECK (char_length(employee) BETWEEN 1 AND 80),
    shift TEXT NOT NULL CHECK (shift IN ('opening', 'midday', 'closing', 'other')),
    notes TEXT NOT NULL DEFAULT '',
    has_image BOOLEAN NOT NULL DEFAULT FALSE,
    image_data BYTEA,
    report_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS briefing_jobs (
    id BIGSERIAL PRIMARY KEY,
    report_id UUID NOT NULL UNIQUE REFERENCES reports(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    locked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS briefings (
    id BIGSERIAL PRIMARY KEY,
    report_id UUID NOT NULL UNIQUE REFERENCES reports(id) ON DELETE CASCADE,
    source_notes TEXT NOT NULL,
    summary TEXT NOT NULL,
    wins TEXT[] NOT NULL DEFAULT '{}',
    risks TEXT[] NOT NULL DEFAULT '{}',
    follow_up TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS briefing_jobs_pending_idx ON briefing_jobs (status, created_at);
