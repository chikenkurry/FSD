import { Errors } from '../common/api-exception';
import { isUuid } from '../common/validation';
import { RoundRepository } from '../rounds/round.repository';
import { AuthorisedMember, SessionAuthoriser } from './session-authoriser';

/**
 * LOCAL DEVELOPMENT AND TESTS ONLY (AppConfig refuses AUTH_MODE=dev in production).
 * Trusts a token of the form "dev:<member-uuid>" and places the member in the round's plan.
 */
export class DevSessionAuthoriser extends SessionAuthoriser {
  constructor(private readonly rounds: RoundRepository) {
    super();
  }

  async authorise(sessionToken: string, roundId: string): Promise<AuthorisedMember> {
    const memberId = sessionToken.startsWith('dev:') ? sessionToken.slice(4) : '';
    if (!isUuid(memberId)) {
      throw Errors.unauthenticated('Dev token must look like "dev:<member-uuid>"');
    }
    const round = await this.rounds.findById(roundId);
    if (!round) throw Errors.forbidden();
    return { memberId, planId: round.planId };
  }
}
