import type { ResponseSnapshotV2 } from '../responses/decision-snapshot';
import type { QuestionDefinitionDto } from '../responses/question-answer';

export type RoundStateValue = 'COLLECTING' | 'FROZEN';

/** The facts about a round that decide whether a write is allowed. */
export interface RoundFacts {
  rosterPolicy?: 'publication' | 'close';
  optionRevision: number;
  state: RoundStateValue;
  questions?: QuestionDefinitionDto[];
  memberIds?: string[];
  currency?: string;
  minorDigits?: number;
  optionSnapshotId?: string | null;
}

export interface RoundRecord extends RoundFacts {
  id: string;
  planId: string;
  activityIds: string[];
  provisionOperationId: string;
  provisionPayloadHash: string;
  freezeOperationId: string | null;
  freezePayloadHash: string | null;
  snapshotId: string | null;
  snapshot: ResponseSnapshotV2 | null;
}

export interface NewRound {
  rosterPolicy?: 'publication' | 'close';
  id: string;
  planId: string;
  optionRevision: number;
  activityIds: string[];
  provisionOperationId: string;
  provisionPayloadHash: string;
  questions?: QuestionDefinitionDto[];
  memberIds?: string[];
  currency?: string;
  minorDigits?: number;
  optionSnapshotId?: string | null;
}

/**
 * Storage port for rounds. Services depend on this abstraction, not on Prisma,
 * so business rules can be unit tested without a database (dependency inversion).
 */
export abstract class RoundRepository {
  abstract findById(id: string): Promise<RoundRecord | null>;

  /** Inserts a COLLECTING round. Resolves null if the round id or provision operation id already exists. */
  abstract create(round: NewRound): Promise<RoundRecord | null>;
}
