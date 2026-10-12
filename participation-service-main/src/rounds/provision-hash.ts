import { createHash } from 'node:crypto';

export interface ProvisionPayload {
  roundId: string;
  planId: string;
  optionRevision: number;
  activityIds: string[];
}

/**
 * Stable fingerprint of what a provision call asked for (excludes the operation ID itself).
 * Activity order does not matter, so a retry that lists them differently is still the same request.
 */
export function hashProvisionPayload(payload: ProvisionPayload): string {
  const canonical = JSON.stringify({
    roundId: payload.roundId.toLowerCase(),
    planId: payload.planId.toLowerCase(),
    optionRevision: payload.optionRevision,
    activityIds: payload.activityIds.map((id) => id.toLowerCase()).sort(),
  });
  return createHash('sha256').update(canonical).digest('hex');
}
