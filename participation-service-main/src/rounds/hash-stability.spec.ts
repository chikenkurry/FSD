import { hashFreezePayload } from './freeze-hash';
import { hashProvisionPayload } from './provision-hash';

/**
 * These fingerprints are stored with each round and compared on every retry, so the way they
 * are computed must never change. If one of these fails, a refactor altered the canonical form
 * and existing rounds would start answering OPERATION_CONFLICT to legitimate retries.
 */
describe('stored fingerprints stay stable', () => {
  it('provision payload', () => {
    expect(
      hashProvisionPayload({
        roundId: 'AAAAAAAA-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        planId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        optionRevision: 3,
        activityIds: ['22222222-2222-4222-8222-222222222222', '11111111-1111-4111-8111-111111111111'],
        memberIds: ['EEEEEEEE-eeee-4eee-8eee-eeeeeeeeeeee', 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'],
        questions: [
          { questionId: '32345678-1234-4234-8234-123456789ABC', required: true, answerFormat: 'text' },
          { questionId: '12345678-1234-4234-8234-123456789abc', required: false, answerFormat: 'choice', choices: ['a', 'b'] },
        ],
        currency: 'USD',
        minorDigits: 2,
        optionSnapshotId: '10101010-1010-4010-8010-101010101010',
        rosterPolicy: 'close',
      }),
    ).toBe('3362c1d2341361c82c0c26eea3caaa2a95dd6ca375859c55307ec199937ff8e5');
  });

  it('freeze payload', () => {
    expect(
      hashFreezePayload({
        roundId: 'AAAAAAAA-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        memberIds: ['EEEEEEEE-eeee-4eee-8eee-eeeeeeeeeeee', 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'],
        optionSnapshotId: '20202020-2020-4020-8020-ABCDEFABCDEF',
        optionRevision: 2,
        requireComplete: true,
        countRespondedOnly: true,
      }),
    ).toBe('51eda14329c9e322f0853fb4ba9a00d04a129654355e7c86b58853f256567005');
  });
});