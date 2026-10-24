import { Injectable } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { Errors } from '../common/api-exception';
import { isUuid } from '../common/validation';
import { ResponseSnapshotV2, toDecisionSnapshot } from '../responses/decision-snapshot';
import { ResponseRepository } from '../responses/response.repository';
import { FreezeRoundDto } from './freeze-round.dto';
import { hashFreezePayload } from './freeze-hash';
import { ProvisionRoundDto } from './provision-round.dto';
import { hashProvisionPayload } from './provision-hash';
import { RoundRecord, RoundRepository } from './round.repository';
import { decisionStatus } from '../responses/response-completeness';

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
  snapshot: ResponseSnapshotV2;
}

export interface ProgressResult {
  roundId: string;
  planId: string;
  optionRevision: number;
  state: string;
  submittedCount: number;
  draftCount: number;
  responses: { memberId: string; status: string; decisionStatus: string }[];
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
    if (dto.rosterPolicy === 'close' && !dto.optionSnapshotId) {
      throw Errors.invalidInput([{ field: 'optionSnapshotId', message: 'A close-roster round needs an immutable form identity' }]);
    }
    const ids = (dto.memberIds ?? []).map(id => id.toLowerCase());
    const qids = (dto.questions ?? []).map(q => q.questionId.toLowerCase());
    if (new Set(ids).size !== ids.length || new Set(qids).size !== qids.length
        || new Set(dto.activityIds.map(id => id.toLowerCase())).size !== dto.activityIds.length) {
      throw Errors.invalidInput([{ field: 'provision', message: 'Identifiers must be unique' }]);
    }
    const hash = hashProvisionPayload(dto);

    const existing = await this.rounds.findById(dto.roundId);
    if (existing) return this.replay(existing, dto.operationId, hash);

    const created = await this.rounds.create({
      rosterPolicy: dto.rosterPolicy ?? 'publication',
      id: dto.roundId,
      planId: dto.planId,
      optionRevision: dto.optionRevision,
      activityIds: dto.activityIds,
      provisionOperationId: dto.operationId,
      provisionPayloadHash: hash,
      questions: dto.questions ?? [],
      memberIds: dto.memberIds ?? [],
      currency: dto.currency ?? "SGD",
      minorDigits: dto.minorDigits ?? 2,
      optionSnapshotId: dto.optionSnapshotId ?? null,
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
      const rejection = await unit.rejectedFreeze(dto.operationId);
      if (rejection) {
        if (rejection !== hash) throw Errors.operationConflict('Rejected close command payload changed');
        return { incomplete: true };
      }
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

      if (unit.round.rosterPolicy !== 'close' && unit.round.memberIds?.length && JSON.stringify([...unit.round.memberIds].map(id => id.toLowerCase()).sort())
          !== JSON.stringify([...dto.memberIds].map(id => id.toLowerCase()).sort())) {
        throw Errors.operationConflict('Freeze roster must match the published roster');
      }
      if (new Set(dto.memberIds.map(id => id.toLowerCase())).size !== dto.memberIds.length) {
        throw Errors.invalidInput([{ field: 'memberIds', message: 'Members must be unique' }]);
      }
      if (dto.optionRevision !== undefined && dto.optionRevision !== unit.round.optionRevision) {
        throw Errors.operationConflict('Freeze option revision must match the published form');
      }
      if (unit.round.rosterPolicy === 'close' && (!dto.optionSnapshotId || dto.optionRevision === undefined)) {
        throw Errors.operationConflict('A close-roster round requires final snapshot identity and revision');
      }
      const stored = await unit.listResponses();
      const snapshotId = randomUUID();
      const snapshot = toDecisionSnapshot({
        snapshotId,
        roundId: unit.round.id,
        planId: unit.round.planId,
        optionRevision: unit.round.optionRevision,
        activityIds: unit.round.activityIds,
        questions: unit.round.questions ?? [],
        currency: unit.round.currency ?? "SGD",
        minorDigits: unit.round.minorDigits ?? 2,
        optionSnapshotId: dto.optionSnapshotId ?? unit.round.optionSnapshotId ?? null,
        memberIds: dto.memberIds,
        responses: stored,
        createdAt: new Date(),
        countRespondedOnly: dto.countRespondedOnly === true,
      });
      // Check while holding the same round lock as writes and freeze. A separate
      // progress check cannot protect against a member editing during closure.
      const counted = snapshot.participants.filter(p => p.is_required_for_decision);
      if ((dto.requireComplete && snapshot.participants.some(p => p.response_status !== 'complete'))
          || (dto.countRespondedOnly && !counted.length)) {
        await unit.rejectFreeze(dto.operationId, hash);
        return { incomplete: true };
      }
      if (Buffer.byteLength(JSON.stringify(snapshot)) > 1_500_000) {
        throw Errors.invalidInput([{ field: 'responses', message: 'Combined snapshot exceeds 1.5 MB; shorten answers or merge availability intervals' }]);
      }
      await unit.freeze({
        memberIds: dto.memberIds,
        optionSnapshotId: dto.optionSnapshotId,
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
    if ('incomplete' in result) throw Errors.responsesIncomplete();
    return result;
  }

  async getSnapshot(roundId: string): Promise<ResponseSnapshotV2> {
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
      .map((r) => ({ memberId: r.memberId, status: r.status,
        decisionStatus: decisionStatus(r, round.optionRevision, round.activityIds, round.questions) }))
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
