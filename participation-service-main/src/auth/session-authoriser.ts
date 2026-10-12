import type { Request } from 'express';

export interface AuthorisedMember {
  memberId: string;
  planId: string;
}

export interface AuthenticatedRequest extends Request {
  requestId: string;
  member?: AuthorisedMember;
}

/**
 * Decides who a session credential belongs to for a given round.
 * Planning owns membership and sessions, so the production implementation asks Planning.
 * Abstract class (not interface) so Nest can use it as a DI token.
 */
export abstract class SessionAuthoriser {
  /**
   * Resolve the credential to a member of the plan that owns `roundId`.
   * Must throw ApiException: UNAUTHENTICATED (bad credential), FORBIDDEN (not a member),
   * UPSTREAM_UNAVAILABLE (cannot decide: fail closed).
   */
  abstract authorise(sessionToken: string, roundId: string): Promise<AuthorisedMember>;
}
