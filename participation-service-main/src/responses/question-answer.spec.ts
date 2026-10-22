import 'reflect-metadata';
import { plainToInstance } from 'class-transformer';
import { validate } from 'class-validator';
import { SaveDraftDto } from './save-draft.dto';
import { aDraft, aRound, MEMBER_1, MEMBER_2, PLAN_ID, ROUND_ID } from '../testing/fixtures';
import { InMemoryResponseRepository, InMemoryRoundRepository } from '../testing/in-memory-repositories';
import { ResponsesService } from './responses.service';
import { RoundsService } from '../rounds/rounds.service';

const questionId = '12345678-1234-4234-8234-123456789abc';
const member = { memberId: MEMBER_1, planId: PLAN_ID };
const questions = [{questionId, required: true, answerFormat: 'text'}];

function setup() {
  const rounds = new InMemoryRoundRepository();
  rounds.rounds.set(ROUND_ID, aRound({questions, memberIds: [MEMBER_1], currency: 'USD'}));
  const responses = new InMemoryResponseRepository(rounds);
  return {rounds, responses, service: new ResponsesService(rounds, responses), lifecycle: new RoundsService(rounds, responses)};
}

it('rejects missing budgets and null required numeric fields before persistence', async () => {
  for (const invalid of [
    {...aDraft(), budget: undefined},
    {...aDraft(), budget: {kind: 'CAP', capMinor: null}},
    {...aDraft(), activityAnswers: [{activityId: aRound().activityIds[0], kind: 'RATING', rating: null}]},
  ]) {
    const errors = await validate(plainToInstance(SaveDraftDto, invalid));
    expect(errors.length).toBeGreaterThan(0);
  }
});

it('keeps question answers and confirmations in the frozen snapshot', async () => {
  const {service, lifecycle} = setup();
  const confirmation = {attribute_id:'access', required_value:true, constraint_rule:'equals_v1', unit:null};
  const saved = await service.saveDraft(ROUND_ID, member, aDraft({activityAnswers:[], budget:{kind:'UNANSWERED'},
    answers:[{question_id:questionId, value:'Step-free access is mandatory', confirmed_requirement:confirmation}]}));
  const submitted = await service.submit(ROUND_ID, member, {expectedRevision:saved.revision});
  expect(submitted.revision).toBe(2);
  const retry = await service.submit(ROUND_ID, member, {expectedRevision:1});
  expect(retry.revision).toBe(2);
  await expect(service.saveDraft(ROUND_ID, member, aDraft({expectedRevision:1}))).rejects.toMatchObject({code:'STALE_VERSION'});
  const frozen = await lifecycle.freeze({roundId:ROUND_ID, operationId:questionId, memberIds:[MEMBER_1]});
  expect(frozen.snapshot.currency).toBe('USD');
  expect(frozen.snapshot.participants[0]).toMatchObject({response_status:'complete', answers:[{confirmed_requirement:confirmation}]});
  expect(JSON.stringify(frozen.snapshot)).not.toContain('quiet please');
});

it('rejects unknown answers, missing required answers and outsiders', async () => {
  const {service} = setup();
  await expect(service.saveDraft(ROUND_ID, member, aDraft({answers:[{question_id:MEMBER_2,value:'x'}]}))).rejects.toMatchObject({code:'INVALID_INPUT'});
  await service.saveDraft(ROUND_ID, member, aDraft({answers:[]}));
  await expect(service.submit(ROUND_ID, member, {expectedRevision:1})).rejects.toMatchObject({code:'INVALID_INPUT'});
  await expect(service.getOwn(ROUND_ID, {memberId:MEMBER_2,planId:PLAN_ID})).rejects.toMatchObject({code:'FORBIDDEN'});
});

it('requires the published roster when freezing', async () => {
  const {lifecycle} = setup();
  await expect(lifecycle.freeze({roundId:ROUND_ID, operationId:questionId, memberIds:[MEMBER_2]})).rejects.toMatchObject({code:'OPERATION_CONFLICT'});
});

describe('direct ratings, importance and early close', () => {
  const ratingId = '22345678-1234-4234-8234-123456789abc';
  function ratingSetup() {
    const rounds = new InMemoryRoundRepository();
    rounds.rounds.set(ROUND_ID, aRound({questions: [{questionId: ratingId, required: true, answerFormat: 'option_rating'}, ...questions],
      memberIds: [MEMBER_1, MEMBER_2], currency: 'USD'}));
    const responses = new InMemoryResponseRepository(rounds);
    return {service: new ResponsesService(rounds, responses), lifecycle: new RoundsService(rounds, responses)};
  }
  const [optionA] = aRound().activityIds;

  it('accepts whole-number ratings and an importance level, and keeps both in the snapshot', async () => {
    const {service, lifecycle} = ratingSetup();
    const saved = await service.saveDraft(ROUND_ID, member, aDraft({activityAnswers: [], budget: {kind: 'UNANSWERED'},
      answers: [{question_id: ratingId, value: {[optionA]: 4}}, {question_id: questionId, value: 'Quiet', importance: 'high'}]}));
    await service.submit(ROUND_ID, member, {expectedRevision: saved.revision});
    const frozen = await lifecycle.freeze({roundId: ROUND_ID, operationId: questionId, memberIds: [MEMBER_1, MEMBER_2], countRespondedOnly: true});
    expect(frozen.snapshot.participants).toEqual(expect.arrayContaining([
      expect.objectContaining({participant_id: MEMBER_1, response_status: 'complete', is_required_for_decision: true,
        answers: expect.arrayContaining([expect.objectContaining({importance: 'high'})])}),
      expect.objectContaining({participant_id: MEMBER_2, response_status: 'incomplete', is_required_for_decision: false}),
    ]));
  });

  it('rejects out-of-range ratings, empty ratings and unknown importance levels', async () => {
    const {service} = ratingSetup();
    for (const value of [{[optionA]: 5}, {[optionA]: 1.5}, [], 'great']) {
      await expect(service.saveDraft(ROUND_ID, member, aDraft({answers: [{question_id: ratingId, value}]})))
        .rejects.toMatchObject({code: 'INVALID_INPUT'});
    }
    const errors = await validate(plainToInstance(SaveDraftDto, aDraft({answers: [{question_id: questionId, value: 'x', importance: 'extreme' as 'high'}]})));
    expect(errors.length).toBeGreaterThan(0);
    await service.saveDraft(ROUND_ID, member, aDraft({activityAnswers: [], budget: {kind: 'UNANSWERED'},
      answers: [{question_id: ratingId, value: {}}, {question_id: questionId, value: 'x'}]}));
    await expect(service.submit(ROUND_ID, member, {expectedRevision: 1})).rejects.toMatchObject({code: 'INVALID_INPUT'});
  });

  it('refuses an early close when nobody has submitted', async () => {
    const {lifecycle} = ratingSetup();
    await expect(lifecycle.freeze({roundId: ROUND_ID, operationId: questionId, memberIds: [MEMBER_1, MEMBER_2], countRespondedOnly: true}))
      .rejects.toMatchObject({code: 'RESPONSES_INCOMPLETE'});
  });
});
