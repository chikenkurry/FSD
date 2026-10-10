-- AlterTable
ALTER TABLE "response_rounds" ADD COLUMN "freeze_operation_id" UUID,
ADD COLUMN "freeze_payload_hash" TEXT,
ADD COLUMN "snapshot_id" UUID,
ADD COLUMN "snapshot" JSONB;

-- CreateIndex
CREATE UNIQUE INDEX "response_rounds_freeze_operation_id_key" ON "response_rounds"("freeze_operation_id");

-- CreateIndex
CREATE UNIQUE INDEX "response_rounds_snapshot_id_key" ON "response_rounds"("snapshot_id");
