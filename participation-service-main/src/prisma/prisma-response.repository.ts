import { Injectable } from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { isUniqueViolation } from '../common/prisma-errors';
import {
  DraftData,
  DraftUnitOfWork,
  FreezeUnitOfWork,
  FreezeWrite,
  ResponseRecord,
  ResponseRepository,
} from '../responses/response.repository';
import { RoundFacts, RoundRecord } from '../rounds/round.repository';
import { PrismaService } from './prisma.service';
import { toRoundRecord } from './prisma-round.repository';

const INCLUDE_CHILDREN = { availability: true, activityAnswers: true } as const;

function scalarFields(data: DraftData) {
  return {
    acknowledgedOptionRevision: data.acknowledgedOptionRevision,
    budgetKind: data.budgetKind,
    budgetCapMinor: data.budgetCapMinor,
    privateNote: data.privateNote,
    answers: (data.answers ?? []) as unknown as Prisma.InputJsonValue,
  };
}

/** One transaction's worth of draft operations, bound to a locked round. */
class PrismaDraftUnitOfWork implements DraftUnitOfWork {
  constructor(
    private readonly tx: Prisma.TransactionClient,
    private readonly roundId: string,
    readonly round: RoundFacts,
  ) {}

  async findExistingId(memberId: string): Promise<string | null> {
    const row = await this.tx.response.findUnique({
      where: { roundId_memberId: { roundId: this.roundId, memberId } },
      select: { id: true },
    });
    return row?.id ?? null;
  }

  async create(memberId: string, data: DraftData): Promise<string | null> {
    try {
      const created = await this.tx.response.create({
        data: {
          roundId: this.roundId,
          memberId,
          revision: 1,
          ...scalarFields(data),
          availability: {
            create: data.availability.map((a) => ({ startAt: a.startAt, endAt: a.endAt })),
          },
          activityAnswers: {
            create: data.activityAnswers.map((a) => ({
              activityId: a.activityId,
              kind: a.kind,
              rating: a.rating,
            })),
          },
        },
        select: { id: true },
      });
      return created.id;
    } catch (error) {
      // Unique (round, member) violated: another first save won. The caller aborts the transaction.
      if (isUniqueViolation(error)) return null;
      throw error;
    }
  }

  async update(responseId: string, expectedRevision: number, data: DraftData): Promise<boolean> {
    const result = await this.tx.response.updateMany({
      where: { id: responseId, revision: expectedRevision },
      data: { ...scalarFields(data), status: 'DRAFT', revision: { increment: 1 } },
    });
    if (result.count === 0) return false;

    await this.tx.availabilityInterval.deleteMany({ where: { responseId } });
    await this.tx.activityAnswer.deleteMany({ where: { responseId } });
    if (data.availability.length > 0) {
      await this.tx.availabilityInterval.createMany({
        data: data.availability.map((a) => ({ responseId, startAt: a.startAt, endAt: a.endAt })),
      });
    }
    if (data.activityAnswers.length > 0) {
      await this.tx.activityAnswer.createMany({
        data: data.activityAnswers.map((a) => ({
          responseId,
          activityId: a.activityId,
          kind: a.kind,
          rating: a.rating,
        })),
      });
    }
    return true;
  }

  async submit(responseId: string, expectedRevision: number): Promise<boolean> {
    const result = await this.tx.response.updateMany({
      where: { id: responseId, revision: expectedRevision },
      data: { status: 'SUBMITTED', revision: { increment: 1 } },
    });
    return result.count === 1;
  }

  load(responseId: string): Promise<ResponseRecord> {
    return this.tx.response.findUniqueOrThrow({
      where: { id: responseId },
      include: INCLUDE_CHILDREN,
    }).then(toResponseRecord);
  }
}

@Injectable()
export class PrismaResponseRepository extends ResponseRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  find(roundId: string, memberId: string): Promise<ResponseRecord | null> {
    return this.prisma.response.findUnique({
      where: { roundId_memberId: { roundId, memberId } },
      include: INCLUDE_CHILDREN,
    }).then(row => row ? toResponseRecord(row) : null);
  }

  listByRound(roundId: string): Promise<ResponseRecord[]> {
    return this.prisma.response.findMany({
      where: { roundId },
      include: INCLUDE_CHILDREN,
    }).then(rows => rows.map(toResponseRecord));
  }

  withRoundWriteLock<T>(
    roundId: string,
    work: (unit: DraftUnitOfWork) => Promise<T>,
  ): Promise<T | null> {
    return this.prisma.$transaction(async (tx) => {
      const rows = await tx.$queryRaw<{ id: string }[]>`
        SELECT id
        FROM response_rounds
        WHERE id = ${roundId}::uuid
        FOR SHARE`;
      const locked = rows[0];
      if (!locked) return null;

      const round = toRoundRecord(await tx.responseRound.findUniqueOrThrow({ where: { id: roundId } }));
      return work(new PrismaDraftUnitOfWork(tx, roundId, round));
    });
  }

  withRoundFreezeLock<T>(
    roundId: string,
    work: (unit: FreezeUnitOfWork) => Promise<T>,
  ): Promise<T | null> {
    return this.prisma.$transaction(async (tx) => {
      const locked = await tx.$queryRaw<{ id: string }[]>`
        SELECT id FROM response_rounds WHERE id = ${roundId}::uuid FOR UPDATE`;
      if (!locked[0]) return null;

      const round = await tx.responseRound.findUniqueOrThrow({ where: { id: roundId } });
      return work(new PrismaFreezeUnitOfWork(tx, toRoundRecord(round)));
    });
  }
}

class PrismaFreezeUnitOfWork implements FreezeUnitOfWork {
  constructor(
    private readonly tx: Prisma.TransactionClient,
    readonly round: RoundRecord,
  ) {}

  listResponses(): Promise<ResponseRecord[]> {
    return this.tx.response.findMany({
      where: { roundId: this.round.id },
      include: INCLUDE_CHILDREN,
    }).then(rows => rows.map(toResponseRecord));
  }

  async freeze(data: FreezeWrite): Promise<void> {
    await this.tx.responseRound.update({
      where: { id: this.round.id },
      data: {
        state: 'FROZEN',
        ...(data.memberIds ? { memberIds: data.memberIds } : {}),
        ...(data.optionSnapshotId ? { optionSnapshotId: data.optionSnapshotId } : {}),
        freezeOperationId: data.freezeOperationId,
        freezePayloadHash: data.freezePayloadHash,
        snapshotId: data.snapshotId,
        snapshot: data.snapshot as Prisma.InputJsonValue,
      },
    });
  }
}

function toResponseRecord(row: Omit<ResponseRecord, "answers"> & { answers: Prisma.JsonValue }): ResponseRecord {
  return { ...row, answers: row.answers as unknown as ResponseRecord["answers"] };
}
