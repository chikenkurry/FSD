import { Injectable } from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { isUniqueViolation } from '../common/prisma-errors';
import { ResponseSnapshotV2 } from '../responses/decision-snapshot';
import { NewRound, RoundRecord, RoundRepository } from '../rounds/round.repository';
import { PrismaService } from './prisma.service';

export function toRoundRecord(row: {
  rosterPolicy?: string;
  id: string;
  planId: string;
  optionRevision: number;
  activityIds: string[];
  questions: Prisma.JsonValue;
  memberIds: string[];
  currency: string;
  minorDigits: number;
  optionSnapshotId: string | null;
  state: RoundRecord['state'];
  provisionOperationId: string;
  provisionPayloadHash: string;
  freezeOperationId: string | null;
  freezePayloadHash: string | null;
  snapshotId: string | null;
  snapshot: Prisma.JsonValue | null;
}): RoundRecord {
  return {
    rosterPolicy: row.rosterPolicy === 'close' ? 'close' : 'publication',
    id: row.id,
    planId: row.planId,
    optionRevision: row.optionRevision,
    activityIds: row.activityIds,
    questions: row.questions as unknown as RoundRecord["questions"],
    memberIds: row.memberIds,
    currency: row.currency,
    minorDigits: row.minorDigits,
    optionSnapshotId: row.optionSnapshotId,
    state: row.state,
    provisionOperationId: row.provisionOperationId,
    provisionPayloadHash: row.provisionPayloadHash,
    freezeOperationId: row.freezeOperationId,
    freezePayloadHash: row.freezePayloadHash,
    snapshotId: row.snapshotId,
    snapshot: (row.snapshot as ResponseSnapshotV2 | null) ?? null,
  };
}

@Injectable()
export class PrismaRoundRepository extends RoundRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  async findById(id: string): Promise<RoundRecord | null> {
    const row = await this.prisma.responseRound.findUnique({ where: { id } });
    return row ? toRoundRecord(row) : null;
  }

  async create(round: NewRound): Promise<RoundRecord | null> {
    try {
      return toRoundRecord(await this.prisma.responseRound.create({ data: { ...round, questions: (round.questions ?? []) as unknown as Prisma.InputJsonValue } }));
    } catch (error) {
      if (isUniqueViolation(error)) return null;
      throw error;
    }
  }
}
