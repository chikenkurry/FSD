import { SaveDraftDto } from '../responses/save-draft.dto';
import { RoundRecord } from '../rounds/round.repository';

export const PLAN_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
export const ROUND_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
export const OPERATION_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
export const ACTIVITY_A = '11111111-1111-4111-8111-111111111111';
export const ACTIVITY_B = '22222222-2222-4222-8222-222222222222';
export const MEMBER_1 = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
export const MEMBER_2 = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';

export function aRound(overrides: Partial<RoundRecord> = {}): RoundRecord {
  return {
    id: ROUND_ID,
    planId: PLAN_ID,
    optionRevision: 1,
    activityIds: [ACTIVITY_A, ACTIVITY_B],
    state: 'COLLECTING',
    provisionOperationId: OPERATION_ID,
    provisionPayloadHash: 'hash',
    freezeOperationId: null,
    freezePayloadHash: null,
    snapshotId: null,
    snapshot: null,
    ...overrides,
  };
}

export function aDraft(overrides: Partial<SaveDraftDto> = {}): SaveDraftDto {
  return {
    expectedRevision: 0,
    acknowledgedOptionRevision: 1,
    availability: [{ startAt: '2026-10-09T11:00:00+08:00', endAt: '2026-10-09T13:00:00+08:00' }],
    budget: { kind: 'CAP', capMinor: 3500 },
    activityAnswers: [
      { activityId: ACTIVITY_A, kind: 'RATING', rating: 4 },
      { activityId: ACTIVITY_B, kind: 'NO_PREFERENCE' },
    ],
    privateNote: 'quiet please',
    ...overrides,
  };
}
