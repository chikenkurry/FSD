CREATE TABLE runs (
    id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE jobs (
    id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, inputs TEXT NOT NULL,
    specification TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued', 'running', 'completed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0, available_at DOUBLE PRECISION NOT NULL,
    lease_until DOUBLE PRECISION, lease_token TEXT, error_code TEXT,
    created_at DOUBLE PRECISION NOT NULL, completed_at DOUBLE PRECISION,
    started_at DOUBLE PRECISION
);
CREATE INDEX jobs_ready ON jobs (specification, state, available_at, created_at);
CREATE TABLE semantic_cache (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE worker_presence (
    id TEXT PRIMARY KEY, specifications TEXT NOT NULL,
    slots INTEGER NOT NULL, last_seen DOUBLE PRECISION NOT NULL
);
CREATE TABLE import_markers (
    source TEXT PRIMARY KEY, summary TEXT NOT NULL
);
