CREATE INDEX jobs_completed_metrics ON jobs (completed_at DESC)
    WHERE completed_at IS NOT NULL;
CREATE INDEX jobs_pending_metrics ON jobs (state, created_at)
    WHERE state IN ('queued', 'running');
CREATE INDEX worker_presence_expiry ON worker_presence (last_seen);
