export type RoundStateValue = 'COLLECTING' | 'FROZEN';

/** The facts about a round that decide whether a write is allowed. */
export interface RoundFacts {
  optionRevision: number;
  state: RoundStateValue;
}

export interface RoundRecord extends RoundFacts {
  id: string;
  planId: string;
  activityIds: string[];
  provisionOperationId: string;
  provisionPayloadHash: string;
}

export interface NewRound {
  id: string;
  planId: string;
  optionRevision: number;
  activityIds: string[];
  provisionOperationId: string;
  provisionPayloadHash: string;
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
