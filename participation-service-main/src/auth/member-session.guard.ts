import { CanActivate, ExecutionContext, Injectable, createParamDecorator } from '@nestjs/common';
import { Errors } from '../common/api-exception';
import { isUuid } from '../common/validation';
import { AppConfig } from '../config/app-config';
import { AuthenticatedRequest, AuthorisedMember, SessionAuthoriser } from './session-authoriser';

function extractToken(req: AuthenticatedRequest, cookieName: string): string | undefined {
  const header = req.header('authorization');
  if (header?.toLowerCase().startsWith('bearer ')) {
    const token = header.slice(7).trim();
    if (token) return token;
  }
  const cookies = req.header('cookie');
  if (cookies) {
    for (const part of cookies.split(';')) {
      const [name, ...rest] = part.trim().split('=');
      if (name === cookieName && rest.length) return decodeURIComponent(rest.join('='));
    }
  }
  return undefined;
}

/**
 * Authenticates the caller for the round in the route (:roundId) and attaches the member.
 * The member is always derived from the credential, never from a client-supplied ID.
 */
@Injectable()
export class MemberSessionGuard implements CanActivate {
  constructor(
    private readonly authoriser: SessionAuthoriser,
    private readonly config: AppConfig,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const req = context.switchToHttp().getRequest<AuthenticatedRequest>();

    const roundId = req.params.roundId;
    if (!isUuid(roundId)) {
      throw Errors.invalidInput([{ field: 'roundId', message: 'roundId must be a UUID' }]);
    }

    const token = extractToken(req, this.config.sessionCookieName);
    if (!token) throw Errors.unauthenticated();

    req.member = await this.authoriser.authorise(token, roundId);
    return true;
  }
}

export const CurrentMember = createParamDecorator(
  (_data: unknown, context: ExecutionContext): AuthorisedMember => {
    return context.switchToHttp().getRequest<AuthenticatedRequest>().member as AuthorisedMember;
  },
);
