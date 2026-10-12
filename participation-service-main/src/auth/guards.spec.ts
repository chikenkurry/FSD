import { ExecutionContext } from '@nestjs/common';
import { AppConfig } from '../config/app-config';
import { InternalTokenGuard } from './internal-token.guard';
import { MemberSessionGuard } from './member-session.guard';
import { AuthorisedMember, SessionAuthoriser } from './session-authoriser';

const ROUND = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

function contextFor(request: Record<string, unknown>): ExecutionContext {
  return { switchToHttp: () => ({ getRequest: () => request }) } as unknown as ExecutionContext;
}

function requestWith(headers: Record<string, string>, params: Record<string, string> = {}) {
  const lower = Object.fromEntries(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]));
  return {
    params,
    header: (name: string) => lower[name.toLowerCase()],
  } as Record<string, unknown> & { member?: AuthorisedMember };
}

describe('MemberSessionGuard', () => {
  const config = { sessionCookieName: 'sess' } as AppConfig;
  const member: AuthorisedMember = { memberId: 'm', planId: 'p' };

  function guardWith(authorise: jest.Mock) {
    const authoriser = { authorise } as unknown as SessionAuthoriser;
    return new MemberSessionGuard(authoriser, config);
  }

  it('authorises a bearer token for the round in the route and attaches the member', async () => {
    const authorise = jest.fn().mockResolvedValue(member);
    const req = requestWith({ authorization: 'Bearer tok-1' }, { roundId: ROUND });
    await expect(guardWith(authorise).canActivate(contextFor(req))).resolves.toBe(true);
    expect(authorise).toHaveBeenCalledWith('tok-1', ROUND);
    expect(req.member).toBe(member);
  });

  it('accepts the session cookie when there is no bearer token', async () => {
    const authorise = jest.fn().mockResolvedValue(member);
    const req = requestWith({ cookie: 'a=1; sess=cookie%2Dtok; b=2' }, { roundId: ROUND });
    await guardWith(authorise).canActivate(contextFor(req));
    expect(authorise).toHaveBeenCalledWith('cookie-tok', ROUND);
  });

  it('rejects a missing credential without calling the authoriser', async () => {
    const authorise = jest.fn();
    const req = requestWith({}, { roundId: ROUND });
    await expect(guardWith(authorise).canActivate(contextFor(req))).rejects.toMatchObject({
      code: 'UNAUTHENTICATED',
    });
    expect(authorise).not.toHaveBeenCalled();
  });

  it('rejects a malformed roundId before contacting the authoriser', async () => {
    const authorise = jest.fn();
    const req = requestWith({ authorization: 'Bearer t' }, { roundId: 'not-a-uuid' });
    await expect(guardWith(authorise).canActivate(contextFor(req))).rejects.toMatchObject({
      code: 'INVALID_INPUT',
    });
    expect(authorise).not.toHaveBeenCalled();
  });

  it('propagates the authoriser failing closed', async () => {
    const authorise = jest.fn().mockRejectedValue(
      Object.assign(new Error('down'), { code: 'UPSTREAM_UNAVAILABLE' }),
    );
    const req = requestWith({ authorization: 'Bearer t' }, { roundId: ROUND });
    await expect(guardWith(authorise).canActivate(contextFor(req))).rejects.toMatchObject({
      code: 'UPSTREAM_UNAVAILABLE',
    });
  });
});

describe('InternalTokenGuard', () => {
  const guard = new InternalTokenGuard({ internalApiToken: 'a-long-enough-secret' } as AppConfig);

  function thrownBy(headers: Record<string, string>): unknown {
    try {
      guard.canActivate(contextFor(requestWith(headers)));
    } catch (error) {
      return error;
    }
    return undefined;
  }

  it('allows the correct token', () => {
    const req = requestWith({ 'x-internal-token': 'a-long-enough-secret' });
    expect(guard.canActivate(contextFor(req))).toBe(true);
  });

  it('rejects a missing token as unauthenticated', () => {
    expect(thrownBy({})).toMatchObject({ code: 'UNAUTHENTICATED' });
  });

  it('rejects a wrong token as forbidden, whatever its length', () => {
    for (const wrong of ['x', 'a-long-enough-secreT', 'a-long-enough-secret-and-more']) {
      expect(thrownBy({ 'x-internal-token': wrong })).toMatchObject({ code: 'FORBIDDEN' });
    }
  });
});
