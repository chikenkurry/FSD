-- Paste this into a second migration created with:
--   npx prisma migrate dev --create-only --name check_constraints
-- then run `npx prisma migrate dev` to apply it.

ALTER TABLE "response_rounds"
  ADD CONSTRAINT "response_rounds_option_revision_positive" CHECK ("option_revision" >= 1);

ALTER TABLE "responses"
  ADD CONSTRAINT "responses_revision_positive" CHECK ("revision" >= 1),
  ADD CONSTRAINT "responses_budget_cap_matches_kind" CHECK (
    ("budget_kind" = 'CAP' AND "budget_cap_minor" IS NOT NULL AND "budget_cap_minor" >= 0)
    OR ("budget_kind" <> 'CAP' AND "budget_cap_minor" IS NULL)
  );

ALTER TABLE "availability_intervals"
  ADD CONSTRAINT "availability_intervals_end_after_start" CHECK ("end_at" > "start_at");

ALTER TABLE "activity_answers"
  ADD CONSTRAINT "activity_answers_rating_matches_kind" CHECK (
    ("kind" = 'RATING' AND "rating" BETWEEN 0 AND 4)
    OR ("kind" <> 'RATING' AND "rating" IS NULL)
  );
