import { Injectable } from '@nestjs/common';
import { AuthorisedMember } from '../auth/session-authoriser';
import { Errors } from '../common/api-exception';
import { RoundFacts, RoundRecord, RoundRepository } from '../rounds/round.repository';
import { completenessErrors, isComplete } from './decision-snapshot';
import { toDraftData } from './draft-data';
import { MyResponseView, emptyView, toView } from './my-response.view';
import { DraftData, DraftUnitOfWork, ResponseRepository } from './response.repository';
import { validateDraft } from './response-rules';
import { SaveDraftDto } from './save-draft.dto';
import { SubmitResponseDto } from './submit-response.dto';

/**
 * Member-facing draft use cases. Holds the business rules; storage and locking sit behind
 * the repository interfaces.
 */
@Injectable()
export class ResponsesService {
  constructor(
    private readonly rounds: RoundRepository,
    private readonly responses: ResponseRepository,
  ) {}

  async getOwn(roundId: string, member: AuthorisedMember): Promise<MyResponseView> {
    const round = await this.requireRound(roundId, member);
    const response = await this.responses.find(roundId, member.memberId);
    return response ? toView(roundId, round, response) : emptyView(roundId, member.memberId, round);
  }

  /**
   * Replaces the caller's draft. Rules, in order:
   *  1. the body is valid (cross-field rules included);
   *  2. under the round lock, the round still accepts responses for the option revision the form used;
   *  3. the caller's revision matches, so another tab's save is never silently overwritten.
   */
  async saveDraft(
    roundId: string,
    member: AuthorisedMember,
    dto: SaveDraftDto,
  ): Promise<MyResponseView> {
    const round = await this.requireRound(roundId, member);

    const problems = validateDraft(dto, round);
    if (problems.length > 0) throw Errors.invalidInput(problems);

    const data = toDraftData(dto);
    const view = await this.responses.withRoundWriteLock(roundId, async (unit) => {
      this.assertAcceptingResponses(unit.round, data.acknowledgedOptionRevision);
      const responseId = await this.writeDraft(unit, member.memberId, dto.expectedRevision, data);
      return toView(roundId, unit.round, await unit.load(responseId));
    });

    if (!view) throw Errors.notFound('Round not found');
    return view;
  }

  /**
   * Marks the caller's current draft as submitted. Completeness is required: every activity
   * answered and budget not UNANSWERED. Empty availability is allowed (unavailable everywhere).
   */
  async submit(
    roundId: string,
    member: AuthorisedMember,
    dto: SubmitResponseDto,
  ): Promise<MyResponseView> {
    const round = await this.requireRound(roundId, member);

    const view = await this.responses.withRoundWriteLock(roundId, async (unit) => {
      this.assertAcceptingResponses(unit.round, unit.round.optionRevision);
      const existingId = await unit.findExistingId(member.memberId);
      if (existingId === null) {
        if (dto.expectedRevision !== 0) throw Errors.staleVersion();
        throw Errors.invalidInput(completenessErrors({ budgetKind: 'UNANSWERED', activityAnswers: [] }, round.activityIds));
      }

      const current = await unit.load(existingId);
      if (current.revision !== dto.expectedRevision) throw Errors.staleVersion();
      if (current.acknowledgedOptionRevision !== unit.round.optionRevision) {
        throw Errors.staleVersion('The options changed; reload the form before submitting');
      }
      if (!isComplete(current, round.activityIds)) {
        throw Errors.invalidInput(completenessErrors(current, round.activityIds));
      }
      if (current.status !== 'SUBMITTED') {
        if (!(await unit.submit(existingId, dto.expectedRevision))) throw Errors.staleVersion();
      }
      return toView(roundId, unit.round, await unit.load(existingId));
    });

    if (!view) throw Errors.notFound('Round not found');
    return view;
  }

  private assertAcceptingResponses(round: RoundFacts, acknowledgedOptionRevision: number): void {
    if (round.state !== 'COLLECTING') throw Errors.roundClosed();
    if (round.optionRevision !== acknowledgedOptionRevision) {
      throw Errors.staleVersion('The options changed; reload the form before saving');
    }
  }

  private async writeDraft(
    unit: DraftUnitOfWork,
    memberId: string,
    expectedRevision: number,
    data: DraftData,
  ): Promise<string> {
    const existingId = await unit.findExistingId(memberId);

    if (existingId === null) {
      if (expectedRevision !== 0) throw Errors.staleVersion();
      const createdId = await unit.create(memberId, data);
      if (createdId === null) throw Errors.staleVersion(); // lost a race with another first save
      return createdId;
    }

    if (!(await unit.update(existingId, expectedRevision, data))) throw Errors.staleVersion();
    return existingId;
  }

  /** The round must be provisioned here and belong to the plan the session was authorised for. */
  private async requireRound(roundId: string, member: AuthorisedMember): Promise<RoundRecord> {
    const round = await this.rounds.findById(roundId);
    if (!round) throw Errors.notFound('This round is not open for responses');
    if (round.planId !== member.planId) throw Errors.forbidden();
    return round;
  }
}
