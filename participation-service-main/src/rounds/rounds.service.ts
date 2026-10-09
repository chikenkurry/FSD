import { Injectable } from '@nestjs/common';
import { Errors } from '../common/api-exception';
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

@Injectable()
export class RoundsService {
  constructor(private readonly rounds: RoundRepository) {}

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
}
