// Turns API codes such as NEEDS_REVIEW into sentence-case labels.
export function stateLabel(value: string) {
  return value
    .toLowerCase()
    .replaceAll('_', ' ')
    .replace(/^./, (c) => c.toUpperCase());
}
