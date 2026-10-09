import { RoundFacts } from '../rounds/round.repository';
import { ResponseRecord } from './response.repository';
import { AnswerKindValue, BudgetKindValue, ResponseStatusValue } from './response.types';

/** Local mirror of MemberResponseV1 (the contract lives with F02; align field names when published). */
export interface MyResponseView {
  roundId: string;
  memberId: string;
  status: ResponseStatusValue;
  /** 0 means "never saved". Send this back as expectedRevision on the next PUT. */
  revision: number;
  acknowledgedOptionRevision: number;
  availability: { startAt: string; endAt: string }[];
  budget: { kind: BudgetKindValue; capMinor: number | null };
  activityAnswers: { activityId: string; kind: AnswerKindValue; rating: number | null }[];
  privateNote: string | null;
  updatedAt: string | null;
  round: RoundFacts;
}

export function toView(roundId: string, round: RoundFacts, response: ResponseRecord): MyResponseView {
  return {
    roundId,
    memberId: response.memberId,
    status: response.status,
    revision: response.revision,
    acknowledgedOptionRevision: response.acknowledgedOptionRevision,
    availability: [...response.availability]
      .sort((a, b) => a.startAt.getTime() - b.startAt.getTime())
      .map((a) => ({ startAt: a.startAt.toISOString(), endAt: a.endAt.toISOString() })),
    budget: { kind: response.budgetKind, capMinor: response.budgetCapMinor },
    activityAnswers: [...response.activityAnswers]
      .sort((a, b) => a.activityId.localeCompare(b.activityId))
      .map((a) => ({ activityId: a.activityId, kind: a.kind, rating: a.rating })),
    privateNote: response.privateNote,
    updatedAt: response.updatedAt.toISOString(),
    round: { optionRevision: round.optionRevision, state: round.state },
  };
}

/** What a member who has not saved anything yet sees. Not persisted. */
export function emptyView(roundId: string, memberId: string, round: RoundFacts): MyResponseView {
  return {
    roundId,
    memberId,
    status: 'DRAFT',
    revision: 0,
    acknowledgedOptionRevision: round.optionRevision,
    availability: [],
    budget: { kind: 'UNANSWERED', capMinor: null },
    activityAnswers: [],
    privateNote: null,
    updatedAt: null,
    round: { optionRevision: round.optionRevision, state: round.state },
  };
}
