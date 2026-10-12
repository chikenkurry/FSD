import { validateDraft } from './response-rules';
import { SaveDraftDto } from './save-draft.dto';

const A1 = '11111111-1111-4111-8111-111111111111';
const A2 = '22222222-2222-4222-8222-222222222222';
const round = { activityIds: [A1, A2] };

function draft(overrides: Partial<SaveDraftDto> = {}): SaveDraftDto {
  return {
    expectedRevision: 0,
    acknowledgedOptionRevision: 1,
    availability: [],
    budget: { kind: 'UNANSWERED' },
    activityAnswers: [],
    ...overrides,
  };
}

const fields = (dto: SaveDraftDto) => validateDraft(dto, round).map((e) => e.field);

describe('validateDraft', () => {
  it('accepts an empty draft (drafts may be partial)', () => {
    expect(validateDraft(draft(), round)).toEqual([]);
  });

  it('accepts adjacent intervals on the 30-minute grid, with any UTC offset', () => {
    const dto = draft({
      availability: [
        { startAt: '2026-10-09T11:00:00+08:00', endAt: '2026-10-09T12:00:00+08:00' },
        { startAt: '2026-10-09T04:00:00Z', endAt: '2026-10-09T04:30:00Z' }, // 12:00-12:30 SGT
      ],
    });
    expect(validateDraft(dto, round)).toEqual([]);
  });

  it('rejects end <= start', () => {
    const dto = draft({
      availability: [{ startAt: '2026-10-09T11:00:00Z', endAt: '2026-10-09T11:00:00Z' }],
    });
    expect(fields(dto)).toContain('availability.0.endAt');
  });

  it('rejects times off the 30-minute grid', () => {
    const dto = draft({
      availability: [{ startAt: '2026-10-09T11:15:00Z', endAt: '2026-10-09T12:00:00Z' }],
    });
    expect(fields(dto)).toContain('availability.0.startAt');
  });

  it('rejects overlapping intervals regardless of input order', () => {
    const dto = draft({
      availability: [
        { startAt: '2026-10-09T12:00:00Z', endAt: '2026-10-09T13:00:00Z' },
        { startAt: '2026-10-09T11:00:00Z', endAt: '2026-10-09T12:30:00Z' },
      ],
    });
    expect(fields(dto)).toContain('availability.0');
  });

  it('requires capMinor for CAP and forbids it otherwise; zero is a valid cap', () => {
    expect(fields(draft({ budget: { kind: 'CAP' } }))).toContain('budget.capMinor');
    expect(fields(draft({ budget: { kind: 'UNLIMITED', capMinor: 100 } }))).toContain(
      'budget.capMinor',
    );
    expect(validateDraft(draft({ budget: { kind: 'CAP', capMinor: 0 } }), round)).toEqual([]);
  });

  it('requires a rating only for RATING answers', () => {
    expect(fields(draft({ activityAnswers: [{ activityId: A1, kind: 'RATING' }] }))).toContain(
      'activityAnswers.0.rating',
    );
    expect(
      fields(draft({ activityAnswers: [{ activityId: A1, kind: 'CANNOT_JOIN', rating: 3 }] })),
    ).toContain('activityAnswers.0.rating');
    expect(
      validateDraft(
        draft({
          activityAnswers: [
            { activityId: A1, kind: 'RATING', rating: 0 },
            { activityId: A2, kind: 'NO_PREFERENCE' },
          ],
        }),
        round,
      ),
    ).toEqual([]);
  });

  it('rejects unknown and duplicate activities', () => {
    const unknown = '33333333-3333-4333-8333-333333333333';
    expect(
      fields(draft({ activityAnswers: [{ activityId: unknown, kind: 'NEEDS_INFO' }] })),
    ).toContain('activityAnswers.0.activityId');
    expect(
      fields(
        draft({
          activityAnswers: [
            { activityId: A1, kind: 'NEEDS_INFO' },
            { activityId: A1, kind: 'CANNOT_JOIN' },
          ],
        }),
      ),
    ).toContain('activityAnswers.1.activityId');
  });
});
