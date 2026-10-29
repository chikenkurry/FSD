import { FieldError } from '../common/api-exception';
import { IdSet } from '../common/ids';
import { ActivityAnswerDto, AvailabilityIntervalDto, BudgetDto, SaveDraftDto } from './save-draft.dto';
import { QuestionDefinitionDto } from './question-answer';
import { validateQuestionAnswers } from './question-answer-rules';

const SLOT_MINUTES = 30;
const SLOT_MS = SLOT_MINUTES * 60_000;

/** Cross-field checks run after DTO validation and retain field error order. */
export function validateDraft(
  dto: SaveDraftDto,
  round: { activityIds: string[]; questions?: QuestionDefinitionDto[]; optionSnapshotId?: string | null },
): FieldError[] {
  if (!dto.budget || typeof dto.budget !== 'object') {
    return [{ field: 'budget', message: 'Budget must be an object' }];
  }
  return [
    ...validateAvailability(dto.availability),
    ...validateBudget(dto.budget),
    ...validateActivityAnswers(dto.activityAnswers, round.activityIds),
    ...(round.optionSnapshotId && dto.activityAnswers.some((a) => a.kind === 'RATING' || a.kind === 'NO_PREFERENCE')
      ? [
          {
            field: 'activityAnswers',
            message: 'ACTIVITY_RATINGS_NOT_SUPPORTED: use published question answers for preferences',
          },
        ]
      : []),
    ...validateQuestionAnswers(dto.answers ?? [], round.questions ?? []),
  ];
}

function validateAvailability(intervals: AvailabilityIntervalDto[]): FieldError[] {
  const errors: FieldError[] = [];
  const parsed = intervals.map((interval, index) => ({
    index,
    start: Date.parse(interval.startAt),
    end: Date.parse(interval.endAt),
  }));

  for (const { index, start, end } of parsed) {
    if (Number.isNaN(start) || Number.isNaN(end)) {
      errors.push({ field: `availability.${index}`, message: 'Invalid date-time' });
      continue;
    }
    if (end <= start) {
      errors.push({ field: `availability.${index}.endAt`, message: 'endAt must be after startAt' });
    }
    if (start % SLOT_MS !== 0) {
      errors.push({
        field: `availability.${index}.startAt`,
        message: `startAt must fall on a ${SLOT_MINUTES}-minute boundary`,
      });
    }
    if (end % SLOT_MS !== 0) {
      errors.push({
        field: `availability.${index}.endAt`,
        message: `endAt must fall on a ${SLOT_MINUTES}-minute boundary`,
      });
    }
  }

  const sorted = parsed.filter((p) => !Number.isNaN(p.start) && !Number.isNaN(p.end)).sort((a, b) => a.start - b.start);
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].start < sorted[i - 1].end) {
      errors.push({
        field: `availability.${sorted[i].index}`,
        message: 'Interval overlaps another interval; merge them or make them adjacent',
      });
    }
  }
  return errors;
}

function validateBudget(budget: BudgetDto): FieldError[] {
  const errors: FieldError[] = [];
  if (budget.kind === 'CAP' && (budget.capMinor == null || !Number.isInteger(budget.capMinor))) {
    errors.push({ field: 'budget.capMinor', message: 'capMinor is required when kind is CAP' });
  }
  if (budget.kind !== 'CAP' && budget.capMinor !== undefined) {
    errors.push({ field: 'budget.capMinor', message: 'capMinor is only allowed when kind is CAP' });
  }
  return errors;
}

function validateActivityAnswers(answers: ActivityAnswerDto[], activityIds: string[]): FieldError[] {
  const errors: FieldError[] = [];
  const allowed = new IdSet(activityIds);
  const seen = new IdSet();
  answers.forEach((answer, index) => {
    if (!allowed.has(answer.activityId)) {
      errors.push({
        field: `activityAnswers.${index}.activityId`,
        message: 'activityId is not part of this round',
      });
    }
    if (seen.has(answer.activityId)) {
      errors.push({
        field: `activityAnswers.${index}.activityId`,
        message: 'activityId appears more than once',
      });
    }
    seen.add(answer.activityId);

    if (answer.kind === 'RATING' && (answer.rating == null || !Number.isInteger(answer.rating))) {
      errors.push({
        field: `activityAnswers.${index}.rating`,
        message: 'rating is required when kind is RATING',
      });
    }
    if (answer.kind !== 'RATING' && answer.rating !== undefined) {
      errors.push({
        field: `activityAnswers.${index}.rating`,
        message: 'rating is only allowed when kind is RATING',
      });
    }
  });
  return errors;
}