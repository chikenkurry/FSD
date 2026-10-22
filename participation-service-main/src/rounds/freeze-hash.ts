import { createHash } from 'node:crypto';

export interface FreezePayload {
  requireComplete?: boolean;
  roundId: string;
  memberIds: string[];
  optionSnapshotId?: string;
  optionRevision?: number;
}

/**
 * Stable fingerprint of a freeze call (excludes the operation ID).
 * Member order does not matter, so a retry that lists the roster differently is the same request.
 */
export function hashFreezePayload(payload: FreezePayload): string {
  const canonical = JSON.stringify({
    ...(payload.requireComplete ? { requireComplete: true } : {}),
    ...(payload.optionSnapshotId ? { optionSnapshotId: payload.optionSnapshotId.toLowerCase() } : {}),
    ...(payload.optionRevision !== undefined ? { optionRevision: payload.optionRevision } : {}),
    roundId: payload.roundId.toLowerCase(),
    memberIds: payload.memberIds.map((id) => id.toLowerCase()).sort(),
  });
  return createHash('sha256').update(canonical).digest('hex');
}
