-- DropForeignKey
ALTER TABLE "rejected_freezes" DROP CONSTRAINT "rejected_freezes_round_id_fkey";

-- AddForeignKey
ALTER TABLE "rejected_freezes" ADD CONSTRAINT "rejected_freezes_round_id_fkey" FOREIGN KEY ("round_id") REFERENCES "response_rounds"("id") ON DELETE CASCADE ON UPDATE CASCADE;
