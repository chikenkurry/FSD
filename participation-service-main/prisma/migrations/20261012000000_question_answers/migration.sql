ALTER TABLE "response_rounds"
  ADD COLUMN "questions" JSONB NOT NULL DEFAULT '[]',
  ADD COLUMN "member_ids" TEXT[] NOT NULL DEFAULT '{}',
  ADD COLUMN "currency" TEXT NOT NULL DEFAULT 'SGD',
  ADD COLUMN "minor_digits" INTEGER NOT NULL DEFAULT 2 CHECK ("minor_digits" BETWEEN 0 AND 9),
  ADD COLUMN "option_snapshot_id" UUID;
ALTER TABLE "responses" ADD COLUMN "answers" JSONB NOT NULL DEFAULT '[]';
ALTER TABLE "activity_answers" DROP CONSTRAINT "activity_answers_rating_matches_kind";
ALTER TABLE "activity_answers" ADD CONSTRAINT "activity_answers_rating_matches_kind" CHECK (
  ("kind" = 'RATING' AND "rating" IS NOT NULL AND "rating" BETWEEN 0 AND 4)
  OR ("kind" <> 'RATING' AND "rating" IS NULL)
);
