import { FieldError } from '../common/api-exception';
import { SaveDraftDto } from './save-draft.dto';

export const SLOT_MINUTES = 30;
const SLOT_MS = SLOT_MINUTES * 60_000;

/**
 * Cross-field rules that decorators cannot express. Pure function: no I/O, easy to unit test.
 * Returns every problem found so the UI can show them all at once.
 */
export function validateDraft(
  dto: SaveDraftDto,
  round: { activityIds: string[] },
): FieldError[] {
  const errors: FieldError[] = [];

  // Availability: ordered, on the 30-minute grid, non-overlapping.
  const parsed = dto.availability.map((interval, index) => ({
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

  const sorted = parsed
    .filter((p) => !Number.isNaN(p.start) && !Number.isNaN(p.end))
    .sort((a, b) => a.start - b.start);
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].start < sorted[i - 1].end) {
      errors.push({
        field: `availability.${sorted[i].index}`,
        message: 'Interval overlaps another interval; merge them or make them adjacent',
      });
    }
  }

  // Budget: a cap amount exists exactly when the kind is CAP.
  if (dto.budget.kind === 'CAP' && dto.budget.capMinor === undefined) {
    errors.push({ field: 'budget.capMinor', message: 'capMinor is required when kind is CAP' });
  }
  if (dto.budget.kind !== 'CAP' && dto.budget.capMinor !== undefined) {
    errors.push({ field: 'budget.capMinor', message: 'capMinor is only allowed when kind is CAP' });
  }

  // Activity answers: known activities, no duplicates, rating only with kind RATING.
  const allowed = new Set(round.activityIds.map((id) => id.toLowerCase()));
  const seen = new Set<string>();
  dto.activityAnswers.forEach((answer, index) => {
    const id = answer.activityId.toLowerCase();
    if (!allowed.has(id)) {
      errors.push({
        field: `activityAnswers.${index}.activityId`,
        message: 'activityId is not part of this round',
      });
    }
    if (seen.has(id)) {
      errors.push({
        field: `activityAnswers.${index}.activityId`,
        message: 'activityId appears more than once',
      });
    }
    seen.add(id);

    if (answer.kind === 'RATING' && answer.rating === undefined) {
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
