import { InMemoryResponseRepository, InMemoryRoundRepository } from '../testing/in-memory-repositories';
import {
  ACTIVITY_A,
  MEMBER_1,
  MEMBER_2,
  PLAN_ID,
  ROUND_ID,
  aDraft,
  aRound,
} from '../testing/fixtures';
import { ResponsesService } from './responses.service';

const member1 = { memberId: MEMBER_1, planId: PLAN_ID };
const member2 = { memberId: MEMBER_2, planId: PLAN_ID };

function setup() {
  const rounds = new InMemoryRoundRepository();
  rounds.rounds.set(ROUND_ID, aRound());
  const responses = new InMemoryResponseRepository(rounds);
  return { rounds, responses, service: new ResponsesService(rounds, responses) };
}

describe('ResponsesService', () => {
  describe('getOwn', () => {
    it('returns an empty revision-0 draft before anything is saved', async () => {
      const { service } = setup();
      await expect(service.getOwn(ROUND_ID, member1)).resolves.toMatchObject({
        memberId: MEMBER_1,
        revision: 0,
        status: 'DRAFT',
        budget: { kind: 'UNANSWERED', capMinor: null },
        availability: [],
        activityAnswers: [],
      });
    });

    it('is not found for a round that was never provisioned', async () => {
      const { service } = setup();
      await expect(
        service.getOwn('99999999-9999-4999-8999-999999999999', member1),
      ).rejects.toMatchObject({ code: 'NOT_FOUND' });
    });

    it("is forbidden for a session from a different plan", async () => {
      const { service } = setup();
      const outsider = { memberId: MEMBER_1, planId: '77777777-7777-4777-8777-777777777777' };
      await expect(service.getOwn(ROUND_ID, outsider)).rejects.toMatchObject({ code: 'FORBIDDEN' });
    });

    it("never returns another member's answers", async () => {
      const { service } = setup();
      await service.saveDraft(ROUND_ID, member1, aDraft());
      const other = await service.getOwn(ROUND_ID, member2);
      expect(other).toMatchObject({ memberId: MEMBER_2, revision: 0, activityAnswers: [] });
      expect(other.privateNote).toBeNull();
    });
  });

  describe('saveDraft', () => {
    it('creates revision 1, then increments on each save', async () => {
      const { service } = setup();
      const first = await service.saveDraft(ROUND_ID, member1, aDraft());
      expect(first.revision).toBe(1);
      expect(first.budget).toEqual({ kind: 'CAP', capMinor: 3500 });

      const second = await service.saveDraft(
        ROUND_ID,
        member1,
        aDraft({ expectedRevision: 1, budget: { kind: 'UNLIMITED' } }),
      );
      expect(second.revision).toBe(2);
      expect(second.budget).toEqual({ kind: 'UNLIMITED', capMinor: null });
    });

    it('replaces the previous answers rather than merging them', async () => {
      const { service } = setup();
      await service.saveDraft(ROUND_ID, member1, aDraft());
      const saved = await service.saveDraft(
        ROUND_ID,
        member1,
        aDraft({
          expectedRevision: 1,
          availability: [],
          activityAnswers: [{ activityId: ACTIVITY_A, kind: 'CANNOT_JOIN' }],
        }),
      );
      expect(saved.availability).toEqual([]);
      expect(saved.activityAnswers).toEqual([
        { activityId: ACTIVITY_A, kind: 'CANNOT_JOIN', rating: null },
      ]);
    });

    it('stores instants in UTC regardless of the offset sent', async () => {
      const { service } = setup();
      const saved = await service.saveDraft(ROUND_ID, member1, aDraft());
      expect(saved.availability).toEqual([
        { startAt: '2026-10-09T03:00:00.000Z', endAt: '2026-10-09T05:00:00.000Z' },
      ]);
    });

    it('rejects a stale revision instead of overwriting', async () => {
      const { service } = setup();
      await service.saveDraft(ROUND_ID, member1, aDraft());
      await expect(
        service.saveDraft(ROUND_ID, member1, aDraft({ expectedRevision: 0 })),
      ).rejects.toMatchObject({ code: 'STALE_VERSION' });
    });

    it('rejects a first save that claims an earlier revision exists', async () => {
      const { service } = setup();
      await expect(
        service.saveDraft(ROUND_ID, member1, aDraft({ expectedRevision: 3 })),
      ).rejects.toMatchObject({ code: 'STALE_VERSION' });
    });

    it('reports STALE_VERSION when another first save wins the race', async () => {
      const { service, responses } = setup();
      responses.loseNextCreateRace = true;
      await expect(service.saveDraft(ROUND_ID, member1, aDraft())).rejects.toMatchObject({
        code: 'STALE_VERSION',
      });
    });

    it('rejects writes once the round is frozen', async () => {
      const { service, rounds } = setup();
      rounds.rounds.set(ROUND_ID, aRound({ state: 'FROZEN' }));
      await expect(service.saveDraft(ROUND_ID, member1, aDraft())).rejects.toMatchObject({
        code: 'ROUND_CLOSED',
      });
    });

    it('rejects a form built from an older option revision', async () => {
      const { service, rounds } = setup();
      rounds.rounds.set(ROUND_ID, aRound({ optionRevision: 2 }));
      await expect(service.saveDraft(ROUND_ID, member1, aDraft())).rejects.toMatchObject({
        code: 'STALE_VERSION',
      });
    });

    it('rejects invalid drafts with field errors and stores nothing', async () => {
      const { service, responses } = setup();
      const error = await service
        .saveDraft(ROUND_ID, member1, aDraft({ budget: { kind: 'CAP' } }))
        .catch((e: unknown) => e);
      expect(error).toMatchObject({
        code: 'INVALID_INPUT',
        fieldErrors: [expect.objectContaining({ field: 'budget.capMinor' })],
      });
      await expect(responses.find(ROUND_ID, MEMBER_1)).resolves.toBeNull();
    });

    it('is forbidden for a session from a different plan', async () => {
      const { service } = setup();
      const outsider = { memberId: MEMBER_1, planId: '77777777-7777-4777-8777-777777777777' };
      await expect(service.saveDraft(ROUND_ID, outsider, aDraft())).rejects.toMatchObject({
        code: 'FORBIDDEN',
      });
    });
  });
});
