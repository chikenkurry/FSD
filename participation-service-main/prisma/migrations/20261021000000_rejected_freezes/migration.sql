CREATE TABLE rejected_freezes (
  round_id UUID NOT NULL REFERENCES response_rounds(id) ON DELETE CASCADE,
  operation_id UUID NOT NULL,
  payload_hash TEXT NOT NULL,
  PRIMARY KEY (round_id, operation_id)
);
