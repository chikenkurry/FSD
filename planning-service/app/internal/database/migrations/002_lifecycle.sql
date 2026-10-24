ALTER TABLE integration_rounds ADD COLUMN roster_policy TEXT NOT NULL DEFAULT 'publication';
ALTER TABLE integration_rounds ADD COLUMN evaluation_definition JSONB;
ALTER TABLE integration_rounds ADD CONSTRAINT roster_policy_valid CHECK (roster_policy IN ('publication', 'close'));
ALTER TABLE integration_rounds ADD CONSTRAINT round_state_valid CHECK (state IN ('PUBLISHING','COLLECTING','LOCKING','REVIEW','CONFIRMED'));

ALTER TABLE selections ADD COLUMN plan_id UUID;
ALTER TABLE selections ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE selections ADD COLUMN option_snapshot_id UUID;
ALTER TABLE selections ADD COLUMN response_snapshot_id TEXT;
ALTER TABLE selections ADD COLUMN details JSONB;
UPDATE selections s SET plan_id=r.plan_id, version=r.option_revision,
  option_snapshot_id=r.option_snapshot_id, response_snapshot_id=r.response_snapshot_id,
  details=jsonb_build_object('historical_definition',r.definition,'candidate_id',s.candidate_id)
  FROM integration_rounds r WHERE r.id=s.round_id;
ALTER TABLE selections ALTER COLUMN plan_id SET NOT NULL;
ALTER TABLE selections ALTER COLUMN option_snapshot_id SET NOT NULL;
ALTER TABLE selections ALTER COLUMN response_snapshot_id SET NOT NULL;
ALTER TABLE selections ALTER COLUMN details SET NOT NULL;
CREATE UNIQUE INDEX selection_plan_version ON selections(plan_id,version);
ALTER TABLE selections ADD CONSTRAINT selection_round_fk FOREIGN KEY(round_id) REFERENCES integration_rounds(id) ON DELETE RESTRICT;

CREATE TABLE round_previews (
  round_id UUID NOT NULL REFERENCES integration_rounds(id) ON DELETE RESTRICT,
  member_id UUID NOT NULL,
  run_id TEXT NOT NULL,
  response_revision INTEGER NOT NULL CHECK (response_revision >= 0),
  PRIMARY KEY(round_id,member_id)
);

CREATE TABLE fact_collection_refs (
  round_id UUID PRIMARY KEY REFERENCES plan_rounds(id) ON DELETE RESTRICT,
  run_id TEXT NOT NULL
);
CREATE TABLE fact_acceptances (
  operation_id UUID PRIMARY KEY,
  target_round_id UUID NOT NULL REFERENCES plan_rounds(id) ON DELETE RESTRICT,
  payload_hash TEXT NOT NULL,
  collection_run_id TEXT NOT NULL,
  reviewed_by UUID NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL
);
