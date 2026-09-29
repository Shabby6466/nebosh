-- Brings databases created from an older db/schema.sql in line with app/models.py.
-- Idempotent: safe to re-run. Apply with:
--   docker compose -f docker-compose.prod.yml exec -T postgres \
--     psql -U postgres -d proctoring < db/migrations/001_pose_gaze_and_client_violations.sql

ALTER TABLE session_frames ADD COLUMN IF NOT EXISTS head_yaw     REAL;
ALTER TABLE session_frames ADD COLUMN IF NOT EXISTS head_pitch   REAL;
ALTER TABLE session_frames ADD COLUMN IF NOT EXISTS gaze_ratio_x REAL;
ALTER TABLE session_frames ADD COLUMN IF NOT EXISTS gaze_ratio_y REAL;

ALTER TYPE violation_type ADD VALUE IF NOT EXISTS 'looking_away';
ALTER TYPE violation_type ADD VALUE IF NOT EXISTS 'tab_switched';
ALTER TYPE violation_type ADD VALUE IF NOT EXISTS 'window_unfocused';
