import {
  DraftData,
  DraftUnitOfWork,
  FreezeUnitOfWork,
  ResponseRecord,
  ResponseRepository,
} from '../responses/response.repository';
import { NewRound, RoundRecord, RoundRepository } from '../rounds/round.repository';

/** Test doubles for the repository ports. Not compiled into the production build. */
export class InMemoryRoundRepository extends RoundRepository {
  readonly rounds = new Map<string, RoundRecord>();

  async findById(id: string): Promise<RoundRecord | null> {
    return this.rounds.get(id) ?? null;
  }

  async create(round: NewRound): Promise<RoundRecord | null> {
    const operationTaken = [...this.rounds.values()].some(
      (r) => r.provisionOperationId === round.provisionOperationId,
    );
    if (this.rounds.has(round.id) || operationTaken) return null;
    const record: RoundRecord = {
      ...round,
      state: 'COLLECTING',
      freezeOperationId: null,
      freezePayloadHash: null,
      snapshotId: null,
      snapshot: null,
    };
    this.rounds.set(round.id, record);
    return record;
  }
}

interface StoredResponse extends ResponseRecord {
  id: string;
  roundId: string;
}

export class InMemoryResponseRepository extends ResponseRepository {
  private readonly stored = new Map<string, StoredResponse>();
  private nextId = 1;

  /** Set to true to make the next create() behave as if another request created the row first. */
  loseNextCreateRace = false;

  constructor(private readonly rounds: InMemoryRoundRepository) {
    super();
  }

  async find(roundId: string, memberId: string): Promise<ResponseRecord | null> {
    const row = this.findRow(roundId, memberId);
    return row ? structuredClone(row) : null;
  }

  async listByRound(roundId: string): Promise<ResponseRecord[]> {
    return [...this.stored.values()]
      .filter((r) => r.roundId === roundId)
      .map((r) => structuredClone(r));
  }

  async withRoundWriteLock<T>(
    roundId: string,
    work: (unit: DraftUnitOfWork) => Promise<T>,
  ): Promise<T | null> {
    const round = this.rounds.rounds.get(roundId);
    if (!round) return null;
    return work(this.unitFor(roundId, { optionRevision: round.optionRevision, state: round.state }));
  }

  private findRow(roundId: string, memberId: string): StoredResponse | undefined {
    return [...this.stored.values()].find((r) => r.roundId === roundId && r.memberId === memberId);
  }

  private unitFor(roundId: string, round: DraftUnitOfWork['round']): DraftUnitOfWork {
    return {
      round,
      findExistingId: async (memberId) => this.findRow(roundId, memberId)?.id ?? null,

      create: async (memberId, data) => {
        if (this.loseNextCreateRace) {
          this.loseNextCreateRace = false;
          return null;
        }
        const id = `response-${this.nextId++}`;
        this.stored.set(id, { id, roundId, memberId, status: 'DRAFT', revision: 1, ...fields(data) });
        return id;
      },

      update: async (responseId, expectedRevision, data) => {
        const row = this.stored.get(responseId);
        if (!row || row.revision !== expectedRevision) return false;
        this.stored.set(responseId, {
          ...row,
          status: 'DRAFT',
          revision: row.revision + 1,
          ...fields(data),
        });
        return true;
      },

      submit: async (responseId, expectedRevision) => {
        const row = this.stored.get(responseId);
        if (!row || row.revision !== expectedRevision) return false;
        this.stored.set(responseId, { ...row, status: 'SUBMITTED', updatedAt: new Date() });
        return true;
      },

      load: async (responseId) => {
        const row = this.stored.get(responseId);
        if (!row) throw new Error(`no response ${responseId}`);
        return structuredClone(row);
      },
    };
  }

  async withRoundFreezeLock<T>(
    roundId: string,
    work: (unit: FreezeUnitOfWork) => Promise<T>,
  ): Promise<T | null> {
    const round = this.rounds.rounds.get(roundId);
    if (!round) return null;
    return work({
      round,
      listResponses: () => this.listByRound(roundId),
      freeze: async (data) => {
        this.rounds.rounds.set(roundId, {
          ...round,
          state: 'FROZEN',
          freezeOperationId: data.freezeOperationId,
          freezePayloadHash: data.freezePayloadHash,
          snapshotId: data.snapshotId,
          snapshot: data.snapshot as RoundRecord['snapshot'],
        });
      },
    });
  }
}

function fields(data: DraftData) {
  return { ...structuredClone(data), updatedAt: new Date() };
}
