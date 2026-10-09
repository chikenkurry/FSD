import { RoundFacts } from '../rounds/round.repository';
import { AnswerKindValue, BudgetKindValue, ResponseStatusValue } from './response.types';

export interface AvailabilityRecord {
  startAt: Date;
  endAt: Date;
}

export interface ActivityAnswerRecord {
  activityId: string;
  kind: AnswerKindValue;
  rating: number | null;
}

/** A stored response as the domain sees it. */
export interface ResponseRecord {
  memberId: string;
  status: ResponseStatusValue;
  revision: number;
  acknowledgedOptionRevision: number;
  budgetKind: BudgetKindValue;
  budgetCapMinor: number | null;
  privateNote: string | null;
  updatedAt: Date;
  availability: AvailabilityRecord[];
  activityAnswers: ActivityAnswerRecord[];
}

/** Everything a draft save replaces. */
export interface DraftData {
  acknowledgedOptionRevision: number;
  budgetKind: BudgetKindValue;
  budgetCapMinor: number | null;
  privateNote: string | null;
  availability: AvailabilityRecord[];
  activityAnswers: ActivityAnswerRecord[];
}

/**
 * Operations available while the round row is locked for writing.
 * Every method belongs to one transaction; the implementation commits or rolls back as a whole.
 */
export interface DraftUnitOfWork {
  /** The round as it is under the lock: this, not an earlier read, decides if the write may proceed. */
  readonly round: RoundFacts;

  findExistingId(memberId: string): Promise<string | null>;

  /** Creates the response at revision 1. Resolves null if the member already has one (lost a race). */
  create(memberId: string, data: DraftData): Promise<string | null>;

  /** Replaces the draft only if its revision still equals `expectedRevision`. Resolves false if not. */
  update(responseId: string, expectedRevision: number, data: DraftData): Promise<boolean>;

  load(responseId: string): Promise<ResponseRecord>;
}

export abstract class ResponseRepository {
  abstract find(roundId: string, memberId: string): Promise<ResponseRecord | null>;

  /**
   * Runs `work` in a transaction holding a shared lock on the round row. Concurrent saves proceed
   * together, while a freeze (which will take an exclusive lock on the same row) waits for them and
   * then blocks later ones. Resolves null if the round does not exist.
   */
  abstract withRoundWriteLock<T>(
    roundId: string,
    work: (unit: DraftUnitOfWork) => Promise<T>,
  ): Promise<T | null>;
}
