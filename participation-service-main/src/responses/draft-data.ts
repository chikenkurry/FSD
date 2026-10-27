import { normaliseId } from '../common/ids';
import { DraftData } from './response.repository';
import { SaveDraftDto } from './save-draft.dto';

/** Maps the validated HTTP body to what the domain stores. Pure, so it is trivial to test. */
export function toDraftData(dto: SaveDraftDto): DraftData {
  return {
    acknowledgedOptionRevision: dto.acknowledgedOptionRevision,
    budgetKind: dto.budget.kind,
    budgetCapMinor: dto.budget.kind === 'CAP' ? (dto.budget.capMinor ?? null) : null,
    privateNote: dto.privateNote ?? null,
    answers: structuredClone(dto.answers ?? []).map(a => ({...a, question_id: normaliseId(a.question_id)})),
    availability: dto.availability.map((a) => ({
      startAt: new Date(a.startAt),
      endAt: new Date(a.endAt),
    })),
    activityAnswers: dto.activityAnswers.map((a) => ({
      activityId: a.activityId,
      kind: a.kind,
      rating: a.kind === 'RATING' ? (a.rating ?? null) : null,
    })),
  };
}