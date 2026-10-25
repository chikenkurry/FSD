ALTER TABLE jobs ADD COLUMN input_summary TEXT;
ALTER TABLE semantic_cache ADD COLUMN created_at DOUBLE PRECISION;
UPDATE semantic_cache SET created_at = EXTRACT(EPOCH FROM clock_timestamp()) WHERE created_at IS NULL;
CREATE INDEX semantic_cache_created ON semantic_cache (created_at);
CREATE TABLE cache_claims (
    key TEXT PRIMARY KEY,
    claimed_at DOUBLE PRECISION NOT NULL
);
