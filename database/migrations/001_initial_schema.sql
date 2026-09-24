-- 001: initial schema. Requires the pgvector extension (see DATABASE.md).
-- Raw camera images are never stored.

-- gen_random_uuid() is built into PostgreSQL 13+. The extension is created by
-- scripts/setup_database.py as the admin user; this line is a no-op afterwards.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS people (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
    external_id  TEXT UNIQUE CHECK (external_id IS NULL OR length(external_id) BETWEEN 1 AND 200),
    status       TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'PENDING', 'DISABLED')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Dimension-less vector column: the dimension is recorded per row and enforced by a CHECK,
-- so embeddings from a future model with a different size can coexist (never compared, see
-- model_name / model_version filters in the search query).
CREATE TABLE IF NOT EXISTS face_embeddings (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id              UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    embedding              vector NOT NULL,
    model_name             TEXT NOT NULL,
    model_version          TEXT NOT NULL,
    embedding_dimension    INTEGER NOT NULL CHECK (embedding_dimension > 0),
    preprocessing_version  TEXT NOT NULL,
    pose                   TEXT CHECK (pose IN ('CENTER', 'LEFT', 'RIGHT', 'UP', 'DOWN')),
    quality_score          REAL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT embedding_dimension_matches CHECK (vector_dims(embedding) = embedding_dimension)
);
CREATE INDEX IF NOT EXISTS ix_face_embeddings_person ON face_embeddings(person_id);
CREATE INDEX IF NOT EXISTS ix_face_embeddings_model ON face_embeddings(model_name, model_version);

CREATE TABLE IF NOT EXISTS recognition_sessions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    UUID NOT NULL UNIQUE,
    session_type  TEXT NOT NULL CHECK (session_type IN ('ENROLLMENT', 'RECOGNITION')),
    person_id     UUID REFERENCES people(id) ON DELETE CASCADE,  -- enrollment target only
    status        TEXT NOT NULL CHECK (status IN ('CREATED', 'IN_PROGRESS', 'PASSED', 'FAILED', 'EXPIRED')),
    failure_code  TEXT,
    challenge     JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    completed_at  TIMESTAMPTZ,
    CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS ix_sessions_status ON recognition_sessions(status);

CREATE TABLE IF NOT EXISTS recognition_results (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        UUID NOT NULL UNIQUE REFERENCES recognition_sessions(session_id) ON DELETE CASCADE,
    person_id         UUID REFERENCES people(id) ON DELETE SET NULL,
    similarity_score  REAL,
    liveness_score    REAL,
    threshold         REAL,
    model_name        TEXT,
    model_version     TEXT,
    result            TEXT NOT NULL CHECK (result IN ('KNOWN', 'UNKNOWN', 'LIVENESS_FAILED', 'CHALLENGE_FAILED',
                                                      'MULTIPLE_FACES', 'EXPIRED', 'ENROLLED')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_results_person ON recognition_results(person_id);

CREATE TABLE IF NOT EXISTS liveness_events (
    id            BIGSERIAL PRIMARY KEY,
    session_id    UUID NOT NULL REFERENCES recognition_sessions(session_id) ON DELETE CASCADE,
    frame_number  INTEGER NOT NULL CHECK (frame_number >= 0),
    score         REAL NOT NULL CHECK (score BETWEEN 0 AND 1),
    prediction    TEXT NOT NULL CHECK (prediction IN ('LIVE', 'SPOOF')),
    stage         TEXT NOT NULL DEFAULT 'PASSIVE',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, frame_number)
);
CREATE INDEX IF NOT EXISTS ix_liveness_session ON liveness_events(session_id);

INSERT INTO schema_migrations(version) VALUES ('001_initial_schema') ON CONFLICT DO NOTHING;
