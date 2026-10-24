// A personal link that signs a guest back in on any device. It carries the
// session secret in the URL fragment (never sent to the server with the page
// request), so it must be kept private like a password.
function encode(value: string) {
  return btoa(unescape(encodeURIComponent(value))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function decode(value: string) {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((value.length + 3) % 4);
  return decodeURIComponent(escape(atob(padded)));
}

export function returnLink(userId: string, token: string, roundId?: string) {
  const params = new URLSearchParams({ ...(roundId ? { round: roundId } : {}), resume: encode(JSON.stringify({ u: userId, t: token })) });
  return `${location.origin}/#${params}`;
}

export function readReturnLink(value: string | null): { userId: string; token: string } | undefined {
  if (!value) return undefined;
  try {
    const parsed = JSON.parse(decode(value)) as { u?: unknown; t?: unknown };
    return typeof parsed.u === 'string' && typeof parsed.t === 'string' && parsed.u && parsed.t ? { userId: parsed.u, token: parsed.t } : undefined;
  } catch { return undefined; }
}
