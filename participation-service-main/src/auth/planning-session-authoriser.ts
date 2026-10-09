import { Logger } from '@nestjs/common';
import { Errors } from '../common/api-exception';
import { isUuid } from '../common/validation';
import { AppConfig } from '../config/app-config';
import { AuthorisedMember, SessionAuthoriser } from './session-authoriser';

const TIMEOUT_MS = 3000;

/**
 * Production authoriser: asks Planning whether this session belongs to a member who may
 * respond in this round's plan. Fails closed: if Planning cannot be reached or answers
 * unexpectedly, the request is rejected (503), never allowed.
 *
 * PROVISIONAL CONTRACT (agree with M1 and put it in contracts/ under F05):
 *   POST {PLANNING_BASE_URL}/internal/sessions/authorise
 *   headers: x-internal-token
 *   body:    { sessionToken: string, roundId: string }
 *   200:     { memberId: uuid, planId: uuid, roundId: uuid, canRespond: boolean }
 *   401/403/404: session unknown, revoked or not a member
 */
export class PlanningSessionAuthoriser extends SessionAuthoriser {
  private readonly logger = new Logger(PlanningSessionAuthoriser.name);

  constructor(private readonly config: AppConfig) {
    super();
  }

  async authorise(sessionToken: string, roundId: string): Promise<AuthorisedMember> {
    let response: Response;
    try {
      response = await fetch(`${this.config.planningBaseUrl}/internal/sessions/authorise`, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-internal-token': this.config.internalApiToken,
        },
        body: JSON.stringify({ sessionToken, roundId }),
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
    } catch (error) {
      this.logger.warn(`Planning unreachable: ${(error as Error).name}`);
      throw Errors.upstreamUnavailable();
    }

    if (response.status === 401) throw Errors.unauthenticated();
    if (response.status === 403 || response.status === 404) throw Errors.forbidden();
    if (!response.ok) {
      this.logger.warn(`Planning answered ${response.status} to authorise`);
      throw Errors.upstreamUnavailable();
    }

    const data = (await response.json().catch(() => null)) as Record<string, unknown> | null;
    if (
      !data ||
      !isUuid(data.memberId) ||
      !isUuid(data.planId) ||
      data.roundId !== roundId ||
      data.canRespond !== true
    ) {
      throw Errors.forbidden();
    }
    return { memberId: data.memberId, planId: data.planId };
  }
}
