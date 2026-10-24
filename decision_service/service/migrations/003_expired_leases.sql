CREATE INDEX jobs_expired_leases ON jobs (lease_until) WHERE state = 'running';
