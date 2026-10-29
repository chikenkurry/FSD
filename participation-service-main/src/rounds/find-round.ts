import { orNotFound } from '../common/api-exception';
import { RoundRecord, RoundRepository } from './round.repository';

/** Loads a round or fails with 404, so callers never repeat the lookup-then-check pair. */
export async function findRoundOrThrow(
  rounds: RoundRepository,
  roundId: string,
  message = 'Round not found',
): Promise<RoundRecord> {
  return orNotFound(await rounds.findById(roundId), message);
}