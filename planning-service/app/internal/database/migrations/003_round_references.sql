ALTER TABLE integration_rounds ADD CONSTRAINT published_draft_fk
  FOREIGN KEY (id) REFERENCES plan_rounds(id) ON DELETE RESTRICT;
ALTER TABLE integration_rounds ADD CONSTRAINT published_plan_fk
  FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE RESTRICT;
