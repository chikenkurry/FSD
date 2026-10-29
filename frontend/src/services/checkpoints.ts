// Tab-local recovery, scoped to the signed-in user. Never store credentials here.
// sessionStorage survives refresh but deliberately does not sync to other devices.
const prefix = 'what2do:checkpoint:v1:';
export function checkpointKey(user: string, scope: string) {
  return `${prefix}${user}:${scope}`;
}
export function readCheckpoint<T>(key: string): T | undefined {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : undefined;
  } catch {
    return undefined;
  }
}
export function writeCheckpoint(key: string, value: unknown): boolean {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}
export function removeCheckpoint(key: string) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* Storage may be unavailable. */
  }
}
export function clearCheckpoints(user: string) {
  try {
    for (const key of Object.keys(sessionStorage))
      if (key.startsWith(`${prefix}${user}:`)) sessionStorage.removeItem(key);
  } catch {
    /* Signing out must still work without storage. */
  }
}
