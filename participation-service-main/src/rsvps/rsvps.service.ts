import { Injectable } from '@nestjs/common';
import { AuthorisedMember } from '../auth/session-authoriser';
import { Errors } from '../common/api-exception';
import { isUniqueViolation } from '../common/prisma-errors';
import { AppConfig } from '../config/app-config';
import { PrismaService } from '../prisma/prisma.service';
import type { SaveRsvpDto } from './rsvps.controller';

@Injectable()
export class RsvpsService {
  constructor(private readonly prisma: PrismaService, private readonly config: AppConfig) {}

  async get(roundId: string, member: AuthorisedMember) {
    const row = await this.prisma.rsvp.findUnique({ where: { roundId_memberId: { roundId, memberId: member.memberId } } });
    return row ?? { roundId, memberId: member.memberId, revision: 0, status: null };
  }

  async save(roundId: string, member: AuthorisedMember, body: SaveRsvpDto) {
    let response: Response;
    try {
      response = await fetch(`${this.config.planningBaseUrl}/internal/rounds/${roundId}/selection`, {
        headers: { 'x-internal-token': this.config.internalApiToken }, signal: AbortSignal.timeout(3000),
      });
    } catch { throw Errors.upstreamUnavailable(); }
    if (response.status === 404 || response.status === 409) throw Errors.operationConflict('Confirm the current selection before answering');
    if (!response.ok) throw Errors.upstreamUnavailable();
    const selection = (await response.json().catch(() => null)) as Record<string, unknown> | null;
    if (!selection || selection.plan_id !== member.planId || selection.round_id !== roundId ||
        selection.selection_version !== body.selectionVersion || selection.is_current !== true) {
      throw Errors.staleVersion('This selection is no longer current');
    }

    // The remote read is outside the local transaction. Any late RSVP remains attached
    // to this exact old selection; it can never become attendance for a reopened round.
    return this.prisma.$transaction(async tx => {
      const where = { roundId_memberId: { roundId, memberId: member.memberId } };
      const current = await tx.rsvp.findUnique({ where });
      if (current && current.revision === body.expectedRevision + 1 &&
          current.selectionVersion === body.selectionVersion && current.status === body.status) return current;
      if (!current) {
        if (body.expectedRevision !== 0) throw Errors.staleVersion();
        try {
          return await tx.rsvp.create({ data: { roundId, memberId: member.memberId,
            selectionVersion: body.selectionVersion, status: body.status } });
        } catch (error) { if (isUniqueViolation(error)) throw Errors.staleVersion(); throw error; }
      }
      const changed = await tx.rsvp.updateMany({
        where: { roundId, memberId: member.memberId, revision: body.expectedRevision, selectionVersion: body.selectionVersion },
        data: { status: body.status, revision: { increment: 1 } },
      });
      if (changed.count !== 1) throw Errors.staleVersion();
      return tx.rsvp.findUniqueOrThrow({ where });
    });
  }
}
