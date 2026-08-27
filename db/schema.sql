-- NEBOSH/IOSH Proctoring Platform — PostgreSQL schema
-- Requires: pgvector extension (embeddings), pgcrypto (uuid gen)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- Candidates
-- ============================================================
CREATE TYPE kyc_status AS ENUM ('pending', 'verified', 'rejected', 'expired');

CREATE TABLE candidates (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name           TEXT NOT NULL,
    email               TEXT NOT NULL UNIQUE,
    phone               TEXT,
    cnic_or_passport_no TEXT NOT NULL,
    exam_booking_ref    TEXT,
    kyc_status          kyc_status NOT NULL DEFAULT 'pending',
    id_document_s3_key  TEXT,           -- encrypted ID scan
    selfie_s3_key       TEXT,           -- encrypted KYC selfie
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_candidates_email ON candidates(email);
CREATE INDEX idx_candidates_kyc_status ON candidates(kyc_status);

-- ============================================================
-- Face embeddings (versioned — re-KYC creates a new active row)
-- ArcFace / InsightFace buffalo_l => 512-dim vector
-- ============================================================
CREATE TABLE face_embeddings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id    UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    embedding       vector(512) NOT NULL,
    match_score     REAL,               -- ID-vs-selfie score at enrollment time
    liveness_score  REAL,
    model_version   TEXT NOT NULL DEFAULT 'arcface-buffalo_l-v1',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_face_embeddings_candidate ON face_embeddings(candidate_id) WHERE is_active;
-- ANN index for similarity search (cosine distance)
CREATE INDEX idx_face_embeddings_vector ON face_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================
-- Exam sessions
-- ============================================================
CREATE TYPE session_status AS ENUM ('active', 'completed', 'terminated', 'abandoned');

CREATE TABLE exam_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id    UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    exam_code       TEXT NOT NULL,       -- e.g. NEBOSH-IGC1
    status          session_status NOT NULL DEFAULT 'active',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    trust_score     REAL,                -- 0-100, computed at session end
    client_ip       TEXT,
    user_agent      TEXT
);

CREATE INDEX idx_sessions_candidate ON exam_sessions(candidate_id);
CREATE INDEX idx_sessions_status ON exam_sessions(status);

-- ============================================================
-- Session frames — lightweight rolling log (NOT every frame's image,
-- just metadata; only violation frames keep an S3 snapshot)
-- ============================================================
CREATE TABLE session_frames (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID NOT NULL REFERENCES exam_sessions(id) ON DELETE CASCADE,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    person_count    SMALLINT,
    face_match      BOOLEAN,
    face_similarity REAL,
    liveness_pass   BOOLEAN,
    processing_ms   INTEGER
);

CREATE INDEX idx_session_frames_session_time ON session_frames(session_id, captured_at);
-- Recommended: partition by month or set a retention job (DELETE older than N days)

-- ============================================================
-- Violations
-- ============================================================
CREATE TYPE violation_type AS ENUM (
    'candidate_missing',
    'multiple_people',
    'face_mismatch',
    'liveness_failed',
    'connection_lost'
);

CREATE TYPE review_status AS ENUM ('unreviewed', 'confirmed', 'false_positive');

CREATE TABLE violations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES exam_sessions(id) ON DELETE CASCADE,
    candidate_id    UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    type            violation_type NOT NULL,
    confidence      REAL,
    snapshot_s3_key TEXT NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    review_status   review_status NOT NULL DEFAULT 'unreviewed',
    reviewed_by     UUID,               -- FK to admins.id, nullable
    reviewed_at     TIMESTAMPTZ,
    review_notes    TEXT
);

CREATE INDEX idx_violations_session ON violations(session_id);
CREATE INDEX idx_violations_candidate ON violations(candidate_id);
CREATE INDEX idx_violations_review_status ON violations(review_status);

-- ============================================================
-- Admin / compliance users
-- ============================================================
CREATE TYPE admin_role AS ENUM ('reviewer', 'compliance_officer', 'admin');

CREATE TABLE admins (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    role            admin_role NOT NULL DEFAULT 'reviewer',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE violations
    ADD CONSTRAINT fk_violations_reviewed_by
    FOREIGN KEY (reviewed_by) REFERENCES admins(id);

-- ============================================================
-- Audit log (append-only, for compliance export)
-- ============================================================
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    candidate_id    UUID REFERENCES candidates(id) ON DELETE SET NULL,
    actor_type      TEXT NOT NULL,       -- 'system' | 'admin' | 'candidate'
    actor_id        UUID,
    action          TEXT NOT NULL,       -- 'kyc_submitted', 'kyc_verified', 'violation_reviewed', ...
    metadata        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_candidate ON audit_log(candidate_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);
