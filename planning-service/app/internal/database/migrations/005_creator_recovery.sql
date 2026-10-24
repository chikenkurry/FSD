-- Wizard metadata belongs to an unpublished round. Options/questions remain in
-- their existing tables; published snapshots and earlier selections are immutable.
ALTER TABLE plan_rounds ADD COLUMN creator_state JSONB;
ALTER TABLE plan_rounds ADD COLUMN source_round_id UUID REFERENCES plan_rounds(id);
