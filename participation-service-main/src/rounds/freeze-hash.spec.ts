import { hashFreezePayload } from './freeze-hash';
import { MEMBER_1, MEMBER_2, ROUND_ID } from '../testing/fixtures';

describe('hashFreezePayload', () => {
  it('ignores member order and UUID case', () => {
    expect(
      hashFreezePayload({ roundId: ROUND_ID, memberIds: [MEMBER_2.toUpperCase(), MEMBER_1] }),
    ).toBe(hashFreezePayload({ roundId: ROUND_ID, memberIds: [MEMBER_1, MEMBER_2] }));
  });
});
