-- Keep the existing report/job schema and status vocabulary intact. Recovery
-- metadata is created lazily at claim time, including for pre-upgrade jobs.
CREATE TABLE IF NOT EXISTS briefing_job_recovery (
    job_id BIGINT PRIMARY KEY REFERENCES briefing_jobs(id) ON DELETE CASCADE,
    lease_token UUID,
    next_attempt_at TIMESTAMPTZ,
    terminal BOOLEAN NOT NULL DEFAULT FALSE
);
