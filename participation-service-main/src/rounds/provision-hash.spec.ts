import { hashProvisionPayload } from './provision-hash';

const base = {
  roundId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  planId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  optionRevision: 1,
  activityIds: [
    '11111111-1111-4111-8111-111111111111',
    '22222222-2222-4222-8222-222222222222',
  ],
};

describe('hashProvisionPayload', () => {
  it('ignores activity order and UUID case', () => {
    const reordered = {
      ...base,
      activityIds: [base.activityIds[1].toUpperCase(), base.activityIds[0]],
    };
    expect(hashProvisionPayload(reordered)).toBe(hashProvisionPayload(base));
  });

  it('changes when the option revision, plan or activities change', () => {
    const original = hashProvisionPayload(base);
    expect(hashProvisionPayload({ ...base, optionRevision: 2 })).not.toBe(original);
    expect(
      hashProvisionPayload({ ...base, planId: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc' }),
    ).not.toBe(original);
    expect(hashProvisionPayload({ ...base, activityIds: [base.activityIds[0]] })).not.toBe(original);
  });
});
