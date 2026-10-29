-- Additive process observations; no changes to existing queue or account data.
CREATE TABLE IF NOT EXISTS runtime_worker_status (
    worker_name TEXT PRIMARY KEY,
    instance_id UUID NOT NULL,
    state TEXT NOT NULL,
    running BOOLEAN NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    last_poll_at TIMESTAMPTZ,
    last_completion_at TIMESTAMPTZ,
    completed_jobs BIGINT NOT NULL DEFAULT 0 CHECK (completed_jobs >= 0),
    consecutive_errors INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_errors >= 0)
);
