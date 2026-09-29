-- Integration fixes: per-organization candidate emails, session mode, per-frame violation.
-- Idempotent: safe to re-run. Run after 001 (session_frames.violation uses its enum values):
--   docker compose -f docker-compose.prod.yml exec -T postgres \
--     psql -U postgres -d proctoring < db/migrations/002_org_scoped_email_session_mode.sql

-- Email unique per organization, case-insensitive (was globally unique, case-sensitive).
-- Fails if one org already has two candidates whose emails differ only by case —
-- resolve those rows first.
ALTER TABLE candidates DROP CONSTRAINT IF EXISTS candidates_email_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_candidates_org_email ON candidates(organization_id, lower(email));
DROP INDEX IF EXISTS idx_candidates_email;

DO $$ BEGIN
    CREATE TYPE session_mode AS ENUM ('exam', 'interview');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
ALTER TABLE exam_sessions ADD COLUMN IF NOT EXISTS mode session_mode NOT NULL DEFAULT 'exam';

ALTER TABLE session_frames ADD COLUMN IF NOT EXISTS violation violation_type;
