-- Scale & ops: durable webhook outbox, and a frame count frozen on the session
-- at end (so reports stay correct after session_frames retention deletes rows).
-- Idempotent: safe to re-run. Run after 002:
--   docker compose -f docker-compose.prod.yml exec -T postgres \
--     psql -U postgres -d proctoring < db/migrations/003_webhook_outbox_and_session_frames_count.sql

ALTER TABLE exam_sessions ADD COLUMN IF NOT EXISTS frames_evaluated INTEGER;

DO $$ BEGIN
    CREATE TYPE webhook_status AS ENUM ('pending', 'delivered', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    event           TEXT NOT NULL,
    payload         JSONB NOT NULL,          -- exact body sent (id, event, created_at, data)
    status          webhook_status NOT NULL DEFAULT 'pending',
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_due
    ON webhook_deliveries(next_attempt_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_org ON webhook_deliveries(organization_id, created_at);
