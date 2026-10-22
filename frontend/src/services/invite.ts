// Accepts a full invitation URL, a bare hash, or its query string.
export function parseInvite(text: string): { round: string; invite: string } | undefined {
  const raw = text.trim();
  if (!raw) return undefined;
  const hash = raw.includes('#') ? raw.slice(raw.indexOf('#') + 1) : raw.replace(/^\?/, '');
  const params = new URLSearchParams(hash);
  const round = params.get('round')?.trim() || '';
  const invite = params.get('invite')?.trim() || '';
  return round && invite ? { round, invite } : undefined;
}
