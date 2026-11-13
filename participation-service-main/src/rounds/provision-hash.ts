import { createHash } from 'node:crypto';
import { canonicalIds, normaliseId } from '../common/ids';
import type { QuestionDefinitionDto } from '../responses/question-answer';

interface ProvisionPayload {
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
    roundId: normaliseId(payload.roundId),
    planId: normaliseId(payload.planId),
    optionRevision: payload.optionRevision,
    activityIds: canonicalIds(payload.activityIds),
    memberIds: canonicalIds(payload.memberIds ?? []),
    questions: [...(payload.questions ?? [])]
      .sort((a, b) => a.questionId.localeCompare(b.questionId))
      .map((q) => ({
        questionId: normaliseId(q.questionId),
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
