ALTER TABLE response_rounds ADD COLUMN roster_policy TEXT NOT NULL DEFAULT 'publication';
ALTER TABLE response_rounds ADD CONSTRAINT roster_policy_valid CHECK (roster_policy IN ('publication', 'close'));
