import type { ResponseRecord } from './response.repository';
import type { AnswerKindValue, BudgetKindValue } from './response.types';
import { QuestionAnswerDto, QuestionDefinitionDto } from './question-answer';
import { decisionStatus } from './response-completeness';

export { decisionStatus, isComplete, completenessErrors } from './response-completeness';
export type { DecisionResponseStatus } from './response-completeness';

/**
 * Immutable snapshot Decision reads after freeze. Field names match
 * `decision_service/algorithm-input-shape.md` so Decision can map this onto
 * `participants`, `constraints`, and `preferences` without renaming.
 *
 * Candidate generation stays in Planning/Decision. Activity-level flags here must be
 * copied onto every candidate of that activity as `candidate_flags` before the algorithm runs.
 */
export interface ResponseSnapshotV2 {
  schema_version: 'response-snapshot-v2';
  option_snapshot_id: string | null;
  currency: string;
  minor_digits: number;
  snapshot_id: string;
  round_id: string;
  plan_id: string;
  option_revision: number;
  created_at: string;
  participants: SnapshotParticipant[];
  constraints: SnapshotConstraint[];
  preferences: SnapshotPreference[];
}

export interface SnapshotParticipant {
  participant_id: string;
  response_status: 'complete' | 'incomplete' | 'stale';
  is_required_for_decision: boolean;
  answers?: QuestionAnswerDto[];
}

export interface SnapshotConstraint {
  participant_id: string;
  availability: { available_intervals: { start_at: string; end_at: string }[] };
  budget: {
    kind: 'limited' | 'unlimited' | 'missing';
    max_cost_minor?: number;
    currency?: string;
  };
  required_attributes: [];
  /** Expand onto candidates of this activity as Decision `candidate_flags`. */
  activity_flags: { activity_id: string; flag: 'cannot_join' | 'needs_information' }[];
  candidate_flags: [];
}

export interface SnapshotPreference {
  participant_id: string;
  activity_id: string;
  rating: 0 | 1 | 2 | 3 | 4;
}

export function toDecisionSnapshot(args: {
  snapshotId: string;
  roundId: string;
  planId: string;
  optionRevision: number;
  activityIds: string[];
  memberIds: string[];
  responses: ResponseRecord[];
  createdAt: Date;
  questions?: QuestionDefinitionDto[];
  currency?: string;
  minorDigits?: number;
  optionSnapshotId?: string | null;
  countRespondedOnly?: boolean;
}): ResponseSnapshotV2 {
  const byMember = new Map(args.responses.map((r) => [r.memberId.toLowerCase(), r]));
  const memberIds = [...args.memberIds].sort((a, b) => a.localeCompare(b));

  const participants: SnapshotParticipant[] = [];
  const constraints: SnapshotConstraint[] = [];
  const preferences: SnapshotPreference[] = [];

  for (const memberId of memberIds) {
    const response = byMember.get(memberId.toLowerCase());
    const status = decisionStatus(response, args.optionRevision, args.activityIds, args.questions);
    participants.push({
      participant_id: memberId,
      response_status: status,
      is_required_for_decision: !args.countRespondedOnly || status === 'complete',
      ...(args.questions?.length ? { answers: structuredClone(response?.answers ?? []) } : {}),
    });
    constraints.push(toConstraint(memberId, response, args.currency ?? 'SGD'));
    if (response) preferences.push(...toPreferences(memberId, response.activityAnswers));
  }

  return {
    schema_version: 'response-snapshot-v2',
    option_snapshot_id: args.optionSnapshotId ?? null,
    currency: args.currency ?? 'SGD',
    minor_digits: args.minorDigits ?? 2,
    snapshot_id: args.snapshotId,
    round_id: args.roundId,
    plan_id: args.planId,
    option_revision: args.optionRevision,
    created_at: args.createdAt.toISOString(),
    participants,
    constraints,
    preferences,
  };
}

function toConstraint(
  participantId: string,
  response: ResponseRecord | undefined,
  currency: string,
): SnapshotConstraint {
  return {
    participant_id: participantId,
    availability: {
      available_intervals: [...(response?.availability ?? [])]
        .sort((a, b) => a.startAt.getTime() - b.startAt.getTime())
        .map((interval) => ({
          start_at: interval.startAt.toISOString(),
          end_at: interval.endAt.toISOString(),
        })),
    },
    budget: toBudget(response?.budgetKind ?? 'UNANSWERED', response?.budgetCapMinor ?? null, currency),
    required_attributes: [],
    activity_flags: toActivityFlags(response?.activityAnswers ?? []),
    candidate_flags: [],
  };
}

function toBudget(kind: BudgetKindValue, capMinor: number | null, currency: string): SnapshotConstraint['budget'] {
  if (kind === 'UNLIMITED') return { kind: 'unlimited', currency };
  if (kind === 'CAP' && capMinor !== null) {
    return { kind: 'limited', max_cost_minor: capMinor, currency };
  }
  return { kind: 'missing', currency };
}

function toActivityFlags(
  answers: { activityId: string; kind: AnswerKindValue }[],
): SnapshotConstraint['activity_flags'] {
  return answers
    .filter((a) => a.kind === 'CANNOT_JOIN' || a.kind === 'NEEDS_INFO')
    .map((a) => ({
      activity_id: a.activityId,
      flag: a.kind === 'CANNOT_JOIN' ? ('cannot_join' as const) : ('needs_information' as const),
    }))
    .sort((a, b) => a.activity_id.localeCompare(b.activity_id));
}

function toPreferences(
  participantId: string,
  answers: { activityId: string; kind: AnswerKindValue; rating: number | null }[],
): SnapshotPreference[] {
  return answers
    .flatMap((a) => {
      if (a.kind === 'RATING' && a.rating !== null) {
        return [
          {
            participant_id: participantId,
            activity_id: a.activityId,
            rating: a.rating as SnapshotPreference['rating'],
          },
        ];
      }
      if (a.kind === 'NO_PREFERENCE') {
        return [{ participant_id: participantId, activity_id: a.activityId, rating: 2 as const }];
      }
      return [];
    })
    .sort((a, b) => a.activity_id.localeCompare(b.activity_id));
}
