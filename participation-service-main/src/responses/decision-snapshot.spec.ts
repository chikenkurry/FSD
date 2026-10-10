import { ACTIVITY_A, ACTIVITY_B, MEMBER_1, MEMBER_2, PLAN_ID, ROUND_ID } from '../testing/fixtures';
import { ResponseRecord } from './response.repository';
import { isComplete, toDecisionSnapshot } from './decision-snapshot';

function aStored(overrides: Partial<ResponseRecord> = {}): ResponseRecord {
  return {
    memberId: MEMBER_1,
    status: 'SUBMITTED',
    revision: 1,
    acknowledgedOptionRevision: 1,
    budgetKind: 'CAP',
    budgetCapMinor: 3500,
    privateNote: 'must never appear',
    updatedAt: new Date('2026-10-09T12:00:00.000Z'),
    availability: [
      { startAt: new Date('2026-10-09T03:00:00.000Z'), endAt: new Date('2026-10-09T05:00:00.000Z') },
    ],
    activityAnswers: [
      { activityId: ACTIVITY_A, kind: 'RATING', rating: 4 },
      { activityId: ACTIVITY_B, kind: 'NEEDS_INFO', rating: null },
    ],
    ...overrides,
  };
}

describe('toDecisionSnapshot', () => {
  it('maps Participation fields onto the Decision algorithm input names', () => {
    const snapshot = toDecisionSnapshot({
      snapshotId: 'snap-1',
      roundId: ROUND_ID,
      planId: PLAN_ID,
      optionRevision: 1,
      activityIds: [ACTIVITY_A, ACTIVITY_B],
      memberIds: [MEMBER_2, MEMBER_1],
      responses: [aStored()],
      createdAt: new Date('2026-10-10T00:00:00.000Z'),
    });

    expect(snapshot.participants).toEqual([
      { participant_id: MEMBER_1, response_status: 'complete', is_required_for_decision: true },
      { participant_id: MEMBER_2, response_status: 'incomplete', is_required_for_decision: true },
    ]);
    expect(snapshot.constraints[0]).toMatchObject({
      participant_id: MEMBER_1,
      budget: { kind: 'limited', max_cost_minor: 3500, currency: 'SGD' },
      activity_flags: [{ activity_id: ACTIVITY_B, flag: 'needs_information' }],
    });
    expect(snapshot.preferences).toEqual([
      { participant_id: MEMBER_1, activity_id: ACTIVITY_A, rating: 4 },
    ]);
    expect(JSON.stringify(snapshot)).not.toContain('must never appear');
  });

  it('maps NO_PREFERENCE to rating 2 and UNLIMITED budget to unlimited', () => {
    const snapshot = toDecisionSnapshot({
      snapshotId: 'snap-1',
      roundId: ROUND_ID,
      planId: PLAN_ID,
      optionRevision: 1,
      activityIds: [ACTIVITY_A, ACTIVITY_B],
      memberIds: [MEMBER_1],
      responses: [
        aStored({
          budgetKind: 'UNLIMITED',
          budgetCapMinor: null,
          activityAnswers: [
            { activityId: ACTIVITY_A, kind: 'NO_PREFERENCE', rating: null },
            { activityId: ACTIVITY_B, kind: 'CANNOT_JOIN', rating: null },
          ],
        }),
      ],
      createdAt: new Date('2026-10-10T00:00:00.000Z'),
    });
    expect(snapshot.constraints[0].budget).toEqual({ kind: 'unlimited', currency: 'SGD' });
    expect(snapshot.preferences).toEqual([
      { participant_id: MEMBER_1, activity_id: ACTIVITY_A, rating: 2 },
    ]);
    expect(snapshot.constraints[0].activity_flags).toEqual([
      { activity_id: ACTIVITY_B, flag: 'cannot_join' },
    ]);
  });
});

describe('isComplete', () => {
  it('requires a budget and an answer for every activity', () => {
    expect(
      isComplete({ budgetKind: 'UNANSWERED', activityAnswers: [{ activityId: ACTIVITY_A }] }, [
        ACTIVITY_A,
        ACTIVITY_B,
      ]),
    ).toBe(false);
    expect(
      isComplete(
        {
          budgetKind: 'UNLIMITED',
          activityAnswers: [{ activityId: ACTIVITY_A }, { activityId: ACTIVITY_B }],
        },
        [ACTIVITY_A, ACTIVITY_B],
      ),
    ).toBe(true);
  });
});
