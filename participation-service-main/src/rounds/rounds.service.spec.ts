import { InMemoryResponseRepository, InMemoryRoundRepository } from '../testing/in-memory-repositories';
import {
  ACTIVITY_A,
  ACTIVITY_B,
  MEMBER_1,
  MEMBER_2,
  OPERATION_ID,
  PLAN_ID,
  ROUND_ID,
  aDraft,
} from '../testing/fixtures';
import { ResponsesService } from '../responses/responses.service';
import { ProvisionRoundDto } from './provision-round.dto';
import { RoundsService } from './rounds.service';

const request = (overrides: Partial<ProvisionRoundDto> = {}): ProvisionRoundDto => ({
  operationId: OPERATION_ID,
  roundId: ROUND_ID,
  planId: PLAN_ID,
  optionRevision: 1,
  activityIds: [ACTIVITY_A, ACTIVITY_B],
  ...overrides,
});

function setup() {
  const rounds = new InMemoryRoundRepository();
  const responses = new InMemoryResponseRepository(rounds);
  return {
    rounds,
    responses,
    service: new RoundsService(rounds, responses),
    members: new ResponsesService(rounds, responses),
  };
}

describe('RoundsService.provision', () => {
  it('opens a new round for responses', async () => {
    const { service, rounds } = setup();
    await expect(service.provision(request())).resolves.toEqual({
      roundId: ROUND_ID,
      planId: PLAN_ID,
      optionRevision: 1,
      state: 'COLLECTING',
      alreadyProvisioned: false,
    });
    expect(rounds.rounds.get(ROUND_ID)?.activityIds).toEqual([ACTIVITY_A, ACTIVITY_B]);
  });

  it('returns the same round when the call is replayed, whatever the activity order', async () => {
    const { service } = setup();
    await service.provision(request());
    await expect(
      service.provision(request({ activityIds: [ACTIVITY_B, ACTIVITY_A] })),
    ).resolves.toMatchObject({ roundId: ROUND_ID, alreadyProvisioned: true });
  });

  it('rejects the same round with a different payload', async () => {
    const { service } = setup();
    await service.provision(request());
    await expect(service.provision(request({ optionRevision: 2 }))).rejects.toMatchObject({
      code: 'OPERATION_CONFLICT',
    });
  });

  it('rejects the same round with a different operationId', async () => {
    const { service } = setup();
    await service.provision(request());
    await expect(
      service.provision(request({ operationId: 'ffffffff-ffff-4fff-8fff-ffffffffffff' })),
    ).rejects.toMatchObject({ code: 'OPERATION_CONFLICT' });
  });

  it('rejects an operationId that already provisioned a different round', async () => {
    const { service } = setup();
    await service.provision(request());
    await expect(
      service.provision(request({ roundId: '12121212-1212-4121-8121-121212121212' })),
    ).rejects.toMatchObject({ code: 'OPERATION_CONFLICT' });
  });

  it('treats losing an insert race to an identical call as a replay', async () => {
    const { service, rounds } = setup();
    await service.provision(request());
    // The first lookup misses (as it would if both calls read before either wrote);
    // the insert then collides and the second lookup finds the winner.
    jest.spyOn(rounds, 'findById').mockResolvedValueOnce(null);
    await expect(service.provision(request())).resolves.toMatchObject({
      alreadyProvisioned: true,
    });
  });
});

describe('RoundsService.freeze', () => {
  const freezeOp = 'f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1';
  const member = { memberId: MEMBER_1, planId: PLAN_ID };

  it('keeps collection open and remembers rejected close commands across later submissions', async () => {
    const { service, members, rounds } = setup();
    await service.provision(request());
    const command = {operationId:freezeOp,roundId:ROUND_ID,memberIds:[MEMBER_1],requireComplete:true};
    await expect(service.freeze(command)).rejects.toMatchObject({code:'RESPONSES_INCOMPLETE'});
    expect(rounds.rounds.get(ROUND_ID)?.state).toBe('COLLECTING');
    await members.saveDraft(ROUND_ID,member,aDraft());
    await members.submit(ROUND_ID,member,{expectedRevision:1});
    // A delayed reconciler retry of the rejected operation remains rejected.
    await expect(service.freeze(command)).rejects.toMatchObject({code:'RESPONSES_INCOMPLETE'});
    expect(rounds.rounds.get(ROUND_ID)?.state).toBe('COLLECTING');
    await expect(service.freeze({...command,memberIds:[MEMBER_1,MEMBER_2]})).rejects.toMatchObject({code:'OPERATION_CONFLICT'});
    await expect(service.freeze({...command,operationId:'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'})).resolves.toMatchObject({state:'FROZEN'});
    await expect(service.freeze(command)).rejects.toMatchObject({code:'RESPONSES_INCOMPLETE'});
  });

  it('freezes the round and returns a Decision-shaped snapshot', async () => {
    const { service, members } = setup();
    await service.provision(request());
    await members.saveDraft(ROUND_ID, member, aDraft());
    await members.submit(ROUND_ID, member, { expectedRevision: 1 });

    const frozen = await service.freeze({
      operationId: freezeOp,
      roundId: ROUND_ID,
      memberIds: [MEMBER_1, MEMBER_2],
    });
    expect(frozen).toMatchObject({ roundId: ROUND_ID, state: 'FROZEN', alreadyFrozen: false });
    expect(frozen.snapshot.participants).toEqual([
      expect.objectContaining({ participant_id: MEMBER_1, response_status: 'complete' }),
      expect.objectContaining({ participant_id: MEMBER_2, response_status: 'incomplete' }),
    ]);
    expect(frozen.snapshot.preferences).toEqual(
      expect.arrayContaining([
        { participant_id: MEMBER_1, activity_id: ACTIVITY_A, rating: 4 },
        { participant_id: MEMBER_1, activity_id: ACTIVITY_B, rating: 2 },
      ]),
    );
    const budget = frozen.snapshot.constraints.find((c) => c.participant_id === MEMBER_1)?.budget;
    expect(budget).toEqual({ kind: 'limited', max_cost_minor: 3500, currency: 'SGD' });
  });

  it('is idempotent for the same operation and roster', async () => {
    const { service } = setup();
    await service.provision(request());
    const first = await service.freeze({
      operationId: freezeOp,
      roundId: ROUND_ID,
      memberIds: [MEMBER_2, MEMBER_1],
    });
    const second = await service.freeze({
      operationId: freezeOp,
      roundId: ROUND_ID,
      memberIds: [MEMBER_1, MEMBER_2],
    });
    expect(second.alreadyFrozen).toBe(true);
    expect(second.snapshotId).toBe(first.snapshotId);
  });

  it('rejects a different roster or operationId after freeze', async () => {
    const { service } = setup();
    await service.provision(request());
    await service.freeze({
      operationId: freezeOp,
      roundId: ROUND_ID,
      memberIds: [MEMBER_1],
    });
    await expect(
      service.freeze({
        operationId: freezeOp,
        roundId: ROUND_ID,
        memberIds: [MEMBER_1, MEMBER_2],
      }),
    ).rejects.toMatchObject({ code: 'OPERATION_CONFLICT' });
  });
});


describe('Final roster admission', () => {
  const formId = '10101010-1010-4010-8010-101010101010';
  const evaluationId = '20202020-2020-4020-8020-202020202020';
  const question = { questionId: ACTIVITY_A, required: true, answerFormat: 'number' };

  it('accepts an authorised late member and freezes the exact final roster and identity', async () => {
    const {service, members} = setup();
    await service.provision(request({rosterPolicy:'close', optionSnapshotId:formId, memberIds:[MEMBER_1], questions:[question]}));
    await members.saveDraft(ROUND_ID, {memberId:MEMBER_2,planId:PLAN_ID}, {
      expectedRevision:0, acknowledgedOptionRevision:1, availability:[],budget:{kind:'UNANSWERED'},
      activityAnswers:[],answers:[{question_id:ACTIVITY_A,value:1.2}],
    });
    await members.submit(ROUND_ID,{memberId:MEMBER_2,planId:PLAN_ID},{expectedRevision:1});
    const body = {operationId:'f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1',roundId:ROUND_ID,
      memberIds:[MEMBER_1,MEMBER_2],optionSnapshotId:evaluationId,optionRevision:1};
    const frozen = await service.freeze(body);
    expect(frozen.snapshot.option_snapshot_id).toBe(evaluationId);
    expect(frozen.snapshot.participants).toEqual(expect.arrayContaining([
      expect.objectContaining({participant_id:MEMBER_2,response_status:'complete'}),
    ]));
    expect((await service.freeze(body)).snapshotId).toBe(frozen.snapshotId);
    await expect(service.freeze({...body,optionSnapshotId:formId})).rejects.toMatchObject({code:'OPERATION_CONFLICT'});
    await expect(members.saveDraft(ROUND_ID,{memberId:MEMBER_2,planId:PLAN_ID},{
      expectedRevision:2,acknowledgedOptionRevision:1,availability:[],budget:{kind:'UNANSWERED'},
      activityAnswers:[],answers:[{question_id:ACTIVITY_A,value:1.2}],
    }))
      .rejects.toMatchObject({code:'ROUND_CLOSED'});
  });

  it('rejects a final snapshot with a different form revision', async () => {
    const {service}=setup();
    await service.provision(request({rosterPolicy:'close',optionSnapshotId:formId,memberIds:[MEMBER_1]}));
    await expect(service.freeze({operationId:'f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1',roundId:ROUND_ID,
      memberIds:[MEMBER_1],optionSnapshotId:evaluationId,optionRevision:2})).rejects.toMatchObject({code:'OPERATION_CONFLICT'});
  });
});
