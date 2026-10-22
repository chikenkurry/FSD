-- Early close: freeze with whoever has submitted. Kept on the round so the
-- reconcile loop retries the same command after a partial failure.
ALTER TABLE integration_rounds ADD COLUMN freeze_counts_responded_only BOOLEAN NOT NULL DEFAULT false;
