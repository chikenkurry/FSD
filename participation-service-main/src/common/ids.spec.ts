import { IdSet, canonicalIds, hasDuplicateIds, normaliseId, sameId, sameIds } from './ids';

const A = '11111111-1111-4111-8111-111111111111';
const B = 'abcdefab-cdef-4bcd-8fab-cdefabcdefab';

describe('identifier helpers', () => {
  it('normalises and compares ignoring case', () => {
    expect(normaliseId(B.toUpperCase())).toBe(B);
    expect(sameId(B, B.toUpperCase())).toBe(true);
    expect(sameId(A, B)).toBe(false);
  });

  it('gives a sorted, lower-cased copy without touching the input', () => {
    const input = [B.toUpperCase(), A];
    expect(canonicalIds(input)).toEqual([A, B]);
    expect(input).toEqual([B.toUpperCase(), A]);
  });

  it('spots duplicates that differ only by case', () => {
    expect(hasDuplicateIds([A, B])).toBe(false);
    expect(hasDuplicateIds([B, B.toUpperCase()])).toBe(true);
    expect(hasDuplicateIds([])).toBe(false);
  });

  it('compares lists as multisets, ignoring order and case', () => {
    expect(sameIds([A, B], [B.toUpperCase(), A])).toBe(true);
    expect(sameIds([A], [A, B])).toBe(false);
    expect(sameIds([A, A], [A, B])).toBe(false);
    expect(sameIds([A, A], [A])).toBe(false);
    expect(sameIds([], [])).toBe(true);
  });
});

describe('IdSet', () => {
  it('matches whatever case went in and whatever case is asked for', () => {
    const set = new IdSet([B.toUpperCase()]);
    expect(set.has(B)).toBe(true);
    expect(set.has(B.toUpperCase())).toBe(true);
    expect(set.has(A)).toBe(false);
  });

  it('can be filled one id at a time', () => {
    const seen = new IdSet();
    expect(seen.has(A)).toBe(false);
    seen.add(A.toUpperCase());
    expect(seen.has(A)).toBe(true);
  });
});
