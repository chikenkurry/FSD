import { Injectable } from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { isUniqueViolation } from '../common/prisma-errors';
import { ResponseSnapshotV1 } from '../responses/decision-snapshot';
import { NewRound, RoundRecord, RoundRepository } from '../rounds/round.repository';
import { PrismaService } from './prisma.service';

function toRoundRecord(row: {
  id: string;
  planId: string;
  optionRevision: number;
  activityIds: string[];
  state: RoundRecord['state'];
  provisionOperationId: string;
  provisionPayloadHash: string;
  freezeOperationId: string | null;
  freezePayloadHash: string | null;
  snapshotId: string | null;
  snapshot: Prisma.JsonValue | null;
}): RoundRecord {
  return {
    id: row.id,
    planId: row.planId,
    optionRevision: row.optionRevision,
    activityIds: row.activityIds,
    state: row.state,
    provisionOperationId: row.provisionOperationId,
    provisionPayloadHash: row.provisionPayloadHash,
    freezeOperationId: row.freezeOperationId,
    freezePayloadHash: row.freezePayloadHash,
    snapshotId: row.snapshotId,
    snapshot: (row.snapshot as ResponseSnapshotV1 | null) ?? null,
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
      return toRoundRecord(await this.prisma.responseRound.create({ data: round }));
    } catch (error) {
      if (isUniqueViolation(error)) return null;
      throw error;
    }
  }
}
