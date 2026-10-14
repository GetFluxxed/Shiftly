-- Store-scoped advisory production forecasts and their independently recoverable queue.
CREATE TABLE store_forecasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    log_id UUID,
    source_fingerprint CHAR(64) NOT NULL,
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','failed')),
    facts JSONB NOT NULL CHECK (jsonb_typeof(facts)='object'),
    source_snapshot JSONB NOT NULL CHECK (jsonb_typeof(source_snapshot)='object'),
    analysis JSONB CHECK (analysis IS NULL OR jsonb_typeof(analysis)='object'),
    error TEXT,
    generated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id,store_id,id),
    UNIQUE (store_id,source_fingerprint,prompt_version,model),
    FOREIGN KEY (store_id,business_id) REFERENCES stores(id,business_id),
    FOREIGN KEY (business_id,store_id,log_id) REFERENCES production_logs(business_id,store_id,id),
    CHECK ((status='ready')=(generated_at IS NOT NULL)),
    CHECK ((status='failed')=(error IS NOT NULL))
);
CREATE INDEX store_forecasts_latest ON store_forecasts(store_id,created_at DESC,id DESC);

CREATE TABLE store_forecast_jobs (
    forecast_id UUID PRIMARY KEY,
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','processing','ready','failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    terminal BOOLEAN NOT NULL DEFAULT FALSE,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((state='processing')=(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)),
    FOREIGN KEY (business_id,store_id,forecast_id) REFERENCES store_forecasts(business_id,store_id,id)
);
CREATE INDEX store_forecast_jobs_claim ON store_forecast_jobs(available_at,created_at)
    WHERE NOT terminal AND state IN ('queued','failed','processing');

CREATE TABLE store_forecast_requests (
    business_id BIGINT NOT NULL,
    store_id BIGINT NOT NULL,
    actor_user_id BIGINT NOT NULL REFERENCES account_users(id),
    request_id UUID NOT NULL,
    fingerprint CHAR(64) NOT NULL,
    forecast_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (business_id,store_id,actor_user_id,request_id),
    FOREIGN KEY (store_id,business_id) REFERENCES stores(id,business_id),
    FOREIGN KEY (business_id,store_id,forecast_id) REFERENCES store_forecasts(business_id,store_id,id)
);
