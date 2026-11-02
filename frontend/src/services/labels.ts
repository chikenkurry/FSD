// Turns API codes such as NEEDS_REVIEW into sentence-case labels.
export function stateLabel(value: string) {
  return value
    .toLowerCase()
    .replaceAll('_', ' ')
    .replace(/^./, (c) => c.toUpperCase());
}

// Long option titles such as “Cumi Bali – Indonesian restaurant in Tanjong Pagar” read as a name and a detail line.
export function splitTitle(title: string): { name: string; detail: string } {
  const match = /^(.{2,60}?)\s+[–—-]\s+(.+)$/.exec(title.trim());
  return match ? { name: match[1]!, detail: match[2]! } : { name: title, detail: '' };
}
