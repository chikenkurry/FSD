import { orNotFound } from './api-exception';
import { assertUuid } from './validation';

describe('assertUuid', () => {
  it('accepts a UUID of either case', () => {
    expect(() => assertUuid('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'roundId')).not.toThrow();
    expect(() => assertUuid('AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA', 'roundId')).not.toThrow();
  });

  it('names the field in the error', () => {
    for (const bad of ['nope', '', undefined, 42]) {
      expect(() => assertUuid(bad, 'roundId')).toThrow(
        expect.objectContaining({
          code: 'INVALID_INPUT',
          fieldErrors: [{ field: 'roundId', message: 'roundId must be a UUID' }],
        }),
      );
    }
  });
});

describe('orNotFound', () => {
  it('returns the value when there is one', () => {
    expect(orNotFound({ id: 1 })).toEqual({ id: 1 });
    expect(orNotFound(0)).toBe(0);
    expect(orNotFound('')).toBe('');
  });

  it('throws NOT_FOUND for null and undefined, with the given message', () => {
    expect(() => orNotFound(null, 'Round not found')).toThrow(
      expect.objectContaining({ code: 'NOT_FOUND', message: 'Round not found' }),
    );
    expect(() => orNotFound(undefined)).toThrow(expect.objectContaining({ code: 'NOT_FOUND' }));
  });
});
