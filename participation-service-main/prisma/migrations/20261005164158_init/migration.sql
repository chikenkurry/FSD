-- CreateEnum
CREATE TYPE "RoundState" AS ENUM ('COLLECTING', 'FROZEN');

-- CreateEnum
CREATE TYPE "ResponseStatus" AS ENUM ('DRAFT', 'SUBMITTED');

-- CreateEnum
CREATE TYPE "BudgetKind" AS ENUM ('UNANSWERED', 'CAP', 'UNLIMITED');

-- CreateEnum
CREATE TYPE "ActivityAnswerKind" AS ENUM ('RATING', 'NO_PREFERENCE', 'CANNOT_JOIN', 'NEEDS_INFO');

-- CreateTable
CREATE TABLE "response_rounds" (
    "id" UUID NOT NULL,
    "plan_id" UUID NOT NULL,
    "option_revision" INTEGER NOT NULL,
    "activity_ids" TEXT[],
    "state" "RoundState" NOT NULL DEFAULT 'COLLECTING',
    "provision_operation_id" UUID NOT NULL,
    "provision_payload_hash" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL,

    CONSTRAINT "response_rounds_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "responses" (
    "id" UUID NOT NULL,
    "round_id" UUID NOT NULL,
    "member_id" UUID NOT NULL,
    "status" "ResponseStatus" NOT NULL DEFAULT 'DRAFT',
    "revision" INTEGER NOT NULL DEFAULT 1,
    "acknowledged_option_revision" INTEGER NOT NULL,
    "budget_kind" "BudgetKind" NOT NULL DEFAULT 'UNANSWERED',
    "budget_cap_minor" INTEGER,
    "private_note" TEXT,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(3) NOT NULL,

    CONSTRAINT "responses_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "availability_intervals" (
    "id" UUID NOT NULL,
    "response_id" UUID NOT NULL,
    "start_at" TIMESTAMPTZ(3) NOT NULL,
    "end_at" TIMESTAMPTZ(3) NOT NULL,

    CONSTRAINT "availability_intervals_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "activity_answers" (
    "id" UUID NOT NULL,
    "response_id" UUID NOT NULL,
    "activity_id" UUID NOT NULL,
    "kind" "ActivityAnswerKind" NOT NULL,
    "rating" INTEGER,

    CONSTRAINT "activity_answers_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "response_rounds_provision_operation_id_key" ON "response_rounds"("provision_operation_id");

-- CreateIndex
CREATE INDEX "response_rounds_plan_id_idx" ON "response_rounds"("plan_id");

-- CreateIndex
CREATE INDEX "responses_round_id_idx" ON "responses"("round_id");

-- CreateIndex
CREATE UNIQUE INDEX "responses_round_id_member_id_key" ON "responses"("round_id", "member_id");

-- CreateIndex
CREATE INDEX "availability_intervals_response_id_idx" ON "availability_intervals"("response_id");

-- CreateIndex
CREATE UNIQUE INDEX "activity_answers_response_id_activity_id_key" ON "activity_answers"("response_id", "activity_id");

-- AddForeignKey
ALTER TABLE "responses" ADD CONSTRAINT "responses_round_id_fkey" FOREIGN KEY ("round_id") REFERENCES "response_rounds"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "availability_intervals" ADD CONSTRAINT "availability_intervals_response_id_fkey" FOREIGN KEY ("response_id") REFERENCES "responses"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "activity_answers" ADD CONSTRAINT "activity_answers_response_id_fkey" FOREIGN KEY ("response_id") REFERENCES "responses"("id") ON DELETE CASCADE ON UPDATE CASCADE;
