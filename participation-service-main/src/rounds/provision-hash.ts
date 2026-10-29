import { createHash } from 'node:crypto';
import type { QuestionDefinitionDto } from '../responses/question-answer';

export interface ProvisionPayload {
  roundId: string;
  planId: string;
  optionRevision: number;
  activityIds: string[];
  questions?: QuestionDefinitionDto[];
  memberIds?: string[];
  currency?: string;
  minorDigits?: number;
  optionSnapshotId?: string;
  rosterPolicy?: 'publication' | 'close';
}

/**
 * Stable fingerprint of what a provision call asked for (excludes the operation ID itself).
 * Activity order does not matter, so a retry that lists them differently is still the same request.
 */
export function hashProvisionPayload(payload: ProvisionPayload): string {
  const canonical = JSON.stringify({
    ...(payload.rosterPolicy === 'close' ? { rosterPolicy: 'close' } : {}),
    roundId: payload.roundId.toLowerCase(),
    planId: payload.planId.toLowerCase(),
    optionRevision: payload.optionRevision,
    activityIds: payload.activityIds.map((id) => id.toLowerCase()).sort(),
    memberIds: (payload.memberIds ?? []).map((id) => id.toLowerCase()).sort(),
    questions: [...(payload.questions ?? [])]
      .sort((a, b) => a.questionId.localeCompare(b.questionId))
      .map((q) => ({
        questionId: q.questionId.toLowerCase(),
        required: q.required,
        answerFormat: q.answerFormat,
        choices: q.choices ?? [],
      })),
    currency: payload.currency ?? 'SGD',
    minorDigits: payload.minorDigits ?? 2,
    optionSnapshotId: payload.optionSnapshotId ?? null,
  });
  return createHash('sha256').update(canonical).digest('hex');
}
