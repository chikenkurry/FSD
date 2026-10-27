import { createHash } from 'node:crypto';
import { canonicalIds, normaliseId } from '../common/ids';

interface FreezePayload {
  requireComplete?: boolean;
  countRespondedOnly?: boolean;
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
    ...(payload.countRespondedOnly ? { countRespondedOnly: true } : {}),
    ...(payload.optionSnapshotId ? { optionSnapshotId: normaliseId(payload.optionSnapshotId) } : {}),
    ...(payload.optionRevision !== undefined ? { optionRevision: payload.optionRevision } : {}),
    roundId: normaliseId(payload.roundId),
    memberIds: canonicalIds(payload.memberIds),
  });
  return createHash('sha256').update(canonical).digest('hex');
}