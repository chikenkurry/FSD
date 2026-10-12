import type { ResponseRecord } from './response.repository';
import type { AnswerKindValue, BudgetKindValue } from './response.types';

/**
 * Immutable snapshot Decision reads after freeze. Field names match
 * `decision_service/algorithm-input-shape.md` so Decision can map this onto
 * `participants`, `constraints`, and `preferences` without renaming.
 *
 * Candidate generation stays in Planning/Decision. Activity-level flags here must be
 * copied onto every candidate of that activity as `candidate_flags` before the algorithm runs.
 */
export interface ResponseSnapshotV1 {
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

export type DecisionResponseStatus = SnapshotParticipant['response_status'];

export function decisionStatus(
  response: ResponseRecord | undefined,
  optionRevision: number,
  activityIds: string[],
): DecisionResponseStatus {
  if (!response) return 'incomplete';
  if (response.acknowledgedOptionRevision !== optionRevision) return 'stale';
  return isComplete(response, activityIds) && response.status === 'SUBMITTED'
    ? 'complete'
    : 'incomplete';
}

export function isComplete(
  response: { budgetKind: BudgetKindValue; activityAnswers: { activityId: string }[] },
  activityIds: string[],
): boolean {
  if (response.budgetKind === 'UNANSWERED') return false;
  const answered = new Set(response.activityAnswers.map((a) => a.activityId.toLowerCase()));
  return activityIds.every((id) => answered.has(id.toLowerCase()));
}

export function completenessErrors(
  response: { budgetKind: BudgetKindValue; activityAnswers: { activityId: string }[] },
  activityIds: string[],
): { field: string; message: string }[] {
  const errors: { field: string; message: string }[] = [];
  if (response.budgetKind === 'UNANSWERED') {
    errors.push({ field: 'budget', message: 'Budget must be a cap or explicit unlimited before submit' });
  }
  const answered = new Set(response.activityAnswers.map((a) => a.activityId.toLowerCase()));
  activityIds.forEach((id, index) => {
    if (!answered.has(id.toLowerCase())) {
      errors.push({
        field: `activityAnswers.${index}`,
        message: `Activity ${id} has no answer`,
      });
    }
  });
  return errors;
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
}): ResponseSnapshotV1 {
  const byMember = new Map(args.responses.map((r) => [r.memberId.toLowerCase(), r]));
  const memberIds = [...args.memberIds].sort((a, b) => a.localeCompare(b));

  const participants: SnapshotParticipant[] = [];
  const constraints: SnapshotConstraint[] = [];
  const preferences: SnapshotPreference[] = [];

  for (const memberId of memberIds) {
    const response = byMember.get(memberId.toLowerCase());
    const status = decisionStatus(response, args.optionRevision, args.activityIds);
    participants.push({
      participant_id: memberId,
      response_status: status,
      is_required_for_decision: true,
    });
    constraints.push(toConstraint(memberId, response));
    if (response) preferences.push(...toPreferences(memberId, response.activityAnswers));
  }

  return {
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

function toConstraint(participantId: string, response: ResponseRecord | undefined): SnapshotConstraint {
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
    budget: toBudget(response?.budgetKind ?? 'UNANSWERED', response?.budgetCapMinor ?? null),
    required_attributes: [],
    activity_flags: toActivityFlags(response?.activityAnswers ?? []),
    candidate_flags: [],
  };
}

function toBudget(
  kind: BudgetKindValue,
  capMinor: number | null,
): SnapshotConstraint['budget'] {
  if (kind === 'UNLIMITED') return { kind: 'unlimited', currency: 'SGD' };
  if (kind === 'CAP' && capMinor !== null) {
    return { kind: 'limited', max_cost_minor: capMinor, currency: 'SGD' };
  }
  return { kind: 'missing', currency: 'SGD' };
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
        return [{ participant_id: participantId, activity_id: a.activityId, rating: a.rating as SnapshotPreference['rating'] }];
      }
      if (a.kind === 'NO_PREFERENCE') {
        return [{ participant_id: participantId, activity_id: a.activityId, rating: 2 as const }];
      }
      return [];
    })
    .sort((a, b) => a.activity_id.localeCompare(b.activity_id));
}
