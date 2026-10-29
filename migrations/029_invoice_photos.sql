-- Private, expiring invoice images and bounded leased extraction jobs.
CREATE TABLE inventory_invoice_photos (
 id UUID PRIMARY KEY, business_id BIGINT NOT NULL, store_id BIGINT NOT NULL, invoice_id UUID NOT NULL,
 actor_user_id BIGINT NOT NULL REFERENCES account_users(id), invoice_version BIGINT NOT NULL,
 image_hash CHAR(64) NOT NULL, image_bytes BYTEA, image_expires_at TIMESTAMPTZ NOT NULL,
 model TEXT NOT NULL, prompt_version TEXT NOT NULL, schema_version TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','ready','failed')),
 message TEXT, proposal JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 FOREIGN KEY (business_id,store_id,invoice_id) REFERENCES inventory_invoice_drafts(business_id,store_id,id),
 CHECK (proposal IS NULL OR jsonb_typeof(proposal)='object'), CHECK (image_bytes IS NOT NULL OR state IN ('ready','failed'))
);
CREATE UNIQUE INDEX inventory_invoice_photos_active_hash ON inventory_invoice_photos(invoice_id,image_hash) WHERE state IN ('queued','running','ready');
CREATE INDEX inventory_invoice_photos_latest ON inventory_invoice_photos(invoice_id,created_at DESC,id DESC);
CREATE TABLE inventory_invoice_photo_jobs (
 photo_id UUID PRIMARY KEY REFERENCES inventory_invoice_photos(id), state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','ready','failed')),
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3), available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 lease_token UUID, lease_expires_at TIMESTAMPTZ, terminal BOOLEAN NOT NULL DEFAULT FALSE, last_error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 CHECK ((state='running')=(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL))
);
CREATE INDEX inventory_invoice_photo_jobs_claim ON inventory_invoice_photo_jobs(available_at,created_at) WHERE NOT terminal;
CREATE TABLE inventory_invoice_photo_requests (
 business_id BIGINT NOT NULL,store_id BIGINT NOT NULL,actor_user_id BIGINT NOT NULL REFERENCES account_users(id),request_id UUID NOT NULL,
 fingerprint CHAR(64) NOT NULL,photo_id UUID NOT NULL REFERENCES inventory_invoice_photos(id),created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(business_id,store_id,actor_user_id,request_id)
);
