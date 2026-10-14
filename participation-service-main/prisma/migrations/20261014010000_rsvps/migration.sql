CREATE TABLE rsvps (
  round_id UUID NOT NULL,
  member_id UUID NOT NULL,
  selection_version INTEGER NOT NULL CHECK (selection_version >= 1),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  status TEXT NOT NULL CHECK (status IN ('GOING', 'MAYBE', 'DECLINED')),
  updated_at TIMESTAMPTZ(3) NOT NULL,
  PRIMARY KEY (round_id, member_id)
);
