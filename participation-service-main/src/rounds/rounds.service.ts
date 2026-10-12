import { Injectable } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { Errors } from '../common/api-exception';
import { isUuid } from '../common/validation';
import { ResponseSnapshotV1, toDecisionSnapshot } from '../responses/decision-snapshot';
import { ResponseRepository } from '../responses/response.repository';
import { FreezeRoundDto } from './freeze-round.dto';
import { hashFreezePayload } from './freeze-hash';
import { ProvisionRoundDto } from './provision-round.dto';
import { hashProvisionPayload } from './provision-hash';
import { RoundRecord, RoundRepository } from './round.repository';

export interface ProvisionResult {
  roundId: string;
  planId: string;
  optionRevision: number;
  state: string;
  /** true when this call was a replay of an earlier identical provision. */
  alreadyProvisioned: boolean;
}

export interface FreezeResult {
  roundId: string;
  snapshotId: string;
  state: 'FROZEN';
  alreadyFrozen: boolean;
  snapshot: ResponseSnapshotV1;
}

export interface ProgressResult {
  roundId: string;
  planId: string;
  optionRevision: number;
  state: string;
  submittedCount: number;
  draftCount: number;
  responses: { memberId: string; status: string }[];
}

@Injectable()
export class RoundsService {
  constructor(
    private readonly rounds: RoundRepository,
    private readonly responses: ResponseRepository,
  ) {}

  /**
   * Idempotent: the same operationId + payload always returns the same round.
   * The same round (or operationId) with a different payload is a conflict.
   * No cross-service calls and no long transaction: one insert guarded by unique keys.
   */
  async provision(dto: ProvisionRoundDto): Promise<ProvisionResult> {
    const hash = hashProvisionPayload(dto);

    const existing = await this.rounds.findById(dto.roundId);
    if (existing) return this.replay(existing, dto.operationId, hash);

    const created = await this.rounds.create({
      id: dto.roundId,
      planId: dto.planId,
      optionRevision: dto.optionRevision,
      activityIds: dto.activityIds,
      provisionOperationId: dto.operationId,
      provisionPayloadHash: hash,
    });
    if (created) return this.view(created, false);

    // Lost a race with a concurrent identical call, or the operationId belongs to another round.
    const winner = await this.rounds.findById(dto.roundId);
    if (winner) return this.replay(winner, dto.operationId, hash);
    throw Errors.operationConflict('operationId was already used for a different round');
  }

  private replay(existing: RoundRecord, operationId: string, hash: string): ProvisionResult {
    if (existing.provisionOperationId !== operationId || existing.provisionPayloadHash !== hash) {
      throw Errors.operationConflict(
        'This round is already provisioned with a different operationId or payload',
      );
    }
    return this.view(existing, true);
  }

  private view(round: RoundRecord, alreadyProvisioned: boolean): ProvisionResult {
    return {
      roundId: round.id,
      planId: round.planId,
      optionRevision: round.optionRevision,
      state: round.state,
      alreadyProvisioned,
    };
  }

  /**
   * Idempotent freeze: locks the round, includes in-flight writes, stores Decision's
   * response snapshot, and rejects later member writes with ROUND_CLOSED.
   */
  async freeze(dto: FreezeRoundDto): Promise<FreezeResult> {
    const hash = hashFreezePayload(dto);
    const result = await this.responses.withRoundFreezeLock(dto.roundId, async (unit) => {
      if (unit.round.state === 'FROZEN') {
        if (unit.round.freezeOperationId !== dto.operationId || unit.round.freezePayloadHash !== hash) {
          throw Errors.operationConflict(
            'This round is already frozen with a different operationId or roster',
          );
        }
        if (!unit.round.snapshotId || !unit.round.snapshot) {
          throw Errors.operationConflict('This round is frozen but has no snapshot');
        }
        return {
          roundId: unit.round.id,
          snapshotId: unit.round.snapshotId,
          state: 'FROZEN' as const,
          alreadyFrozen: true,
          snapshot: unit.round.snapshot,
        };
      }

      const stored = await unit.listResponses();
      const snapshotId = randomUUID();
      const snapshot = toDecisionSnapshot({
        snapshotId,
        roundId: unit.round.id,
        planId: unit.round.planId,
        optionRevision: unit.round.optionRevision,
        activityIds: unit.round.activityIds,
        memberIds: dto.memberIds,
        responses: stored,
        createdAt: new Date(),
      });
      await unit.freeze({
        freezeOperationId: dto.operationId,
        freezePayloadHash: hash,
        snapshotId,
        snapshot,
      });
      return {
        roundId: unit.round.id,
        snapshotId,
        state: 'FROZEN' as const,
        alreadyFrozen: false,
        snapshot,
      };
    });

    if (!result) throw Errors.notFound('This round is not open for responses');
    return result;
  }

  async getSnapshot(roundId: string): Promise<ResponseSnapshotV1> {
    if (!isUuid(roundId)) {
      throw Errors.invalidInput([{ field: 'roundId', message: 'roundId must be a UUID' }]);
    }
    const round = await this.rounds.findById(roundId);
    if (!round) throw Errors.notFound('Round not found');
    if (!round.snapshot) throw Errors.notFound('No response snapshot; freeze the round first');
    return round.snapshot;
  }

  async progress(roundId: string): Promise<ProgressResult> {
    if (!isUuid(roundId)) {
      throw Errors.invalidInput([{ field: 'roundId', message: 'roundId must be a UUID' }]);
    }
    const round = await this.rounds.findById(roundId);
    if (!round) throw Errors.notFound('Round not found');
    const stored = await this.responses.listByRound(roundId);
    const responses = stored
      .map((r) => ({ memberId: r.memberId, status: r.status }))
      .sort((a, b) => a.memberId.localeCompare(b.memberId));
    return {
      roundId: round.id,
      planId: round.planId,
      optionRevision: round.optionRevision,
      state: round.state,
      submittedCount: responses.filter((r) => r.status === 'SUBMITTED').length,
      draftCount: responses.filter((r) => r.status === 'DRAFT').length,
      responses,
    };
  }
}
