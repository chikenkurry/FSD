import { Injectable } from '@nestjs/common';
import { createHash } from 'node:crypto';
import { AuthorisedMember } from '../auth/session-authoriser';
import { Errors, orNotFound } from '../common/api-exception';
import { IdSet, sameId } from '../common/ids';
import { findRoundOrThrow } from '../rounds/find-round';
import { RoundFacts, RoundRecord, RoundRepository } from '../rounds/round.repository';
import { completenessErrors, isComplete } from './response-completeness';
import { toDraftData } from './draft-data';
import { MyResponseView, emptyView, toView } from './my-response.view';
import { DraftData, DraftUnitOfWork, ResponseRepository } from './response.repository';
import { validateDraft } from './response-rules';
import { SaveDraftDto } from './save-draft.dto';
import { SubmitResponseDto } from './submit-response.dto';
import { toDecisionSnapshot } from './decision-snapshot';

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

  async copyDraft(roundId: string, sourceRoundId: string, member: AuthorisedMember): Promise<MyResponseView> {
    const round = await this.requireRound(roundId, member);
    const source = await this.requireRound(sourceRoundId, member);
    if (roundId === sourceRoundId || round.optionRevision <= source.optionRevision) {
      throw Errors.invalidInput([{ field: 'sourceRoundId', message: 'Copy from an earlier round of this plan' }]);
    }
    const stored = await this.responses.find(sourceRoundId, member.memberId);
    if (!stored) throw Errors.notFound('No earlier response to copy');
    const knownQuestions = new IdSet((round.questions ?? []).map((q) => q.questionId));
    const knownActivities = new IdSet(round.activityIds);
    const sameMoneyConvention = round.currency === source.currency && round.minorDigits === source.minorDigits;
    const data: DraftData = {
      acknowledgedOptionRevision: source.optionRevision,
      budgetKind: sameMoneyConvention ? stored.budgetKind : 'UNANSWERED',
      budgetCapMinor: sameMoneyConvention ? stored.budgetCapMinor : null,
      privateNote: stored.privateNote,
      availability: structuredClone(stored.availability),
      activityAnswers: stored.activityAnswers.filter((a) => knownActivities.has(a.activityId)),
      answers: (stored.answers ?? [])
        .filter((a) => knownQuestions.has(a.question_id))
        .map((a) => ({ question_id: a.question_id, value: structuredClone(a.value) })),
    };
    const view = await this.responses.withRoundWriteLock(roundId, async (unit) => {
      if (unit.round.state !== 'COLLECTING') throw Errors.roundClosed();
      if (await unit.findExistingId(member.memberId))
        throw Errors.operationConflict('A draft already exists; copying cannot overwrite it');
      const id = await unit.create(member.memberId, data);
      if (!id) throw Errors.staleVersion();
      return toView(roundId, unit.round, await unit.load(id));
    });
    return orNotFound(view, 'Round not found');
  }

  /**
   * Replaces the caller's draft. Rules, in order:
   *  1. the body is valid (cross-field rules included);
   *  2. under the round lock, the round still accepts responses for the option revision the form used;
   *  3. the caller's revision matches, so another tab's save is never silently overwritten.
   */
  async saveDraft(roundId: string, member: AuthorisedMember, dto: SaveDraftDto): Promise<MyResponseView> {
    const round = await this.requireRound(roundId, member);

    const problems = validateDraft(dto, round);
    if (problems.length > 0) throw Errors.invalidInput(problems);

    const data = toDraftData(dto);
    const view = await this.responses.withRoundWriteLock(roundId, async (unit) => {
      this.assertAcceptingResponses(unit.round, data.acknowledgedOptionRevision);
      if (
        unit.round.rosterPolicy === 'close' &&
        (data.answers ?? []).some(
          (a) => a.confirmed_requirement !== undefined || a.confirmed_requirements !== undefined,
        )
      ) {
        const existingId = await unit.findExistingId(member.memberId);
        const current = existingId ? await unit.load(existingId) : null;
        for (const answer of data.answers ?? []) {
          if (answer.confirmed_requirement === undefined && answer.confirmed_requirements === undefined) continue;
          const previous = current?.answers?.find((a) => a.question_id === answer.question_id);
          if (
            answer.reviewed_revision !== dto.expectedRevision ||
            !previous ||
            JSON.stringify(previous.value) !== JSON.stringify(answer.value)
          ) {
            throw Errors.staleVersion(
              'Save the answer, preview its current revision, then confirm that interpretation',
            );
          }
        }
      }
      const responseId = await this.writeDraft(unit, member.memberId, dto.expectedRevision, data);
      return toView(roundId, unit.round, await unit.load(responseId));
    });

    return orNotFound(view, 'Round not found');
  }

  /** Internal-only projection; identity is supplied by Planning, never by a public caller. */
  async previewSnapshot(roundId: string, memberId: string) {
    const round = await findRoundOrThrow(this.rounds, roundId);
    const snapshot = await this.responses.withRoundWriteLock(roundId, async (unit) => {
      if (unit.round.state !== 'COLLECTING') throw Errors.roundClosed();
      const responseId = await unit.findExistingId(memberId);
      const current = responseId ? await unit.load(responseId) : null;
      const revision = current?.revision ?? 0;
      const snapshotId = createHash('sha256').update(`${roundId}:${memberId}:${revision}`).digest('hex');
      return {
        ...toDecisionSnapshot({
          snapshotId,
          roundId,
          planId: round.planId,
          optionRevision: round.optionRevision,
          activityIds: round.activityIds,
          memberIds: [memberId],
          responses: current ? [current] : [],
          createdAt: current?.updatedAt ?? new Date(0),
          questions: round.questions,
          currency: round.currency,
          minorDigits: round.minorDigits,
          optionSnapshotId: round.optionSnapshotId,
        }),
        response_revision: revision,
      };
    });
    return orNotFound(snapshot, 'Round not found');
  }

  /**
   * Submits a complete draft. Published question forms require their required
   * answers; legacy activity forms require each activity and an explicit budget.
   */
  async submit(roundId: string, member: AuthorisedMember, dto: SubmitResponseDto): Promise<MyResponseView> {
    const round = await this.requireRound(roundId, member);

    const view = await this.responses.withRoundWriteLock(roundId, async (unit) => {
      this.assertAcceptingResponses(unit.round, unit.round.optionRevision);
      const existingId = await unit.findExistingId(member.memberId);
      if (existingId === null) {
        if (dto.expectedRevision !== 0) throw Errors.staleVersion();
        throw Errors.invalidInput(
          completenessErrors({ budgetKind: 'UNANSWERED', activityAnswers: [] }, round.activityIds),
        );
      }

      const current = await unit.load(existingId);
      // A lost submit response can be retried with the pre-submit revision.
      if (current.status === 'SUBMITTED' && current.revision === dto.expectedRevision + 1) {
        return toView(roundId, unit.round, current);
      }
      if (current.revision !== dto.expectedRevision) throw Errors.staleVersion();
      if (current.acknowledgedOptionRevision !== unit.round.optionRevision) {
        throw Errors.staleVersion('The options changed; reload the form before submitting');
      }
      if (!isComplete(current, round.activityIds, round.questions)) {
        if (round.questions?.length)
          throw Errors.invalidInput([{ field: 'answers', message: 'Answer all required questions before submitting' }]);
        throw Errors.invalidInput(completenessErrors(current, round.activityIds));
      }
      if (current.status !== 'SUBMITTED') {
        if (!(await unit.submit(existingId, dto.expectedRevision))) throw Errors.staleVersion();
      }
      return toView(roundId, unit.round, await unit.load(existingId));
    });

    return orNotFound(view, 'Round not found');
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
    const round = await findRoundOrThrow(this.rounds, roundId, 'This round is not open for responses');
    if (round.planId !== member.planId) throw Errors.forbidden();
    if (
      (round.rosterPolicy !== 'close' || round.state === 'FROZEN') &&
      round.memberIds?.length &&
      !round.memberIds.some((id) => sameId(id, member.memberId))
    ) {
      throw Errors.forbidden();
    }
    return round;
  }
}
