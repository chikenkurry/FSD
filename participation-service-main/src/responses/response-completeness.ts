import type { ResponseRecord } from './response.repository';
import type { BudgetKindValue } from './response.types';
import type { QuestionAnswerDto, QuestionDefinitionDto } from './question-answer';
import { answeredRequiredQuestions } from './question-answer-rules';

export type DecisionResponseStatus = 'complete' | 'incomplete' | 'stale';

export function decisionStatus(
  response: ResponseRecord | undefined,
  optionRevision: number,
  activityIds: string[],
  questions: QuestionDefinitionDto[] = [],
): DecisionResponseStatus {
  if (!response) return 'incomplete';
  if (response.acknowledgedOptionRevision !== optionRevision) return 'stale';
  return isComplete(response, activityIds, questions) && response.status === 'SUBMITTED'
    ? 'complete'
    : 'incomplete';
}

export function isComplete(
  response: { budgetKind: BudgetKindValue; activityAnswers: { activityId: string }[]; answers?: QuestionAnswerDto[] },
  activityIds: string[],
  questions: QuestionDefinitionDto[] = [],
): boolean {
  if (questions.length > 0) return answeredRequiredQuestions(response.answers ?? [], questions);
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
