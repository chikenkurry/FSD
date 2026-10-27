/**
 * Identifiers (UUIDs) reach this service in mixed case from different callers, and every
 * comparison must ignore case. Doing that through these helpers, rather than calling
 * `.toLowerCase()` at each site, means nobody has to remember to normalise both sides.
 */

/** The single canonical spelling of an identifier. */
export function normaliseId(id: string): string {
  return id.toLowerCase();
}

export function sameId(a: string, b: string): boolean {
  return normaliseId(a) === normaliseId(b);
}

/** Normalised and sorted: the canonical form of a list of identifiers (fingerprints, roster checks). */
export function canonicalIds(ids: readonly string[]): string[] {
  return ids.map(normaliseId).sort();
}

/** True when the same identifier appears twice, ignoring case. */
export function hasDuplicateIds(ids: readonly string[]): boolean {
  return new Set(ids.map(normaliseId)).size !== ids.length;
}

/** True when both lists hold the same identifiers (any order, any case, duplicates counted). */
export function sameIds(a: readonly string[], b: readonly string[]): boolean {
  const left = canonicalIds(a);
  const right = canonicalIds(b);
  return left.length === right.length && left.every((id, index) => id === right[index]);
}

/** A set of identifiers that normalises on the way in and on the way out. */
export class IdSet {
  private readonly ids = new Set<string>();

  constructor(ids: Iterable<string> = []) {
    for (const id of ids) this.add(id);
  }

  add(id: string): this {
    this.ids.add(normaliseId(id));
    return this;
  }

  has(id: string): boolean {
    return this.ids.has(normaliseId(id));
  }
}