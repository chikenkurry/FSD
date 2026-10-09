import { InMemoryRoundRepository } from '../testing/in-memory-repositories';
import { ACTIVITY_A, ACTIVITY_B, OPERATION_ID, PLAN_ID, ROUND_ID } from '../testing/fixtures';
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
  return { rounds, service: new RoundsService(rounds) };
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
