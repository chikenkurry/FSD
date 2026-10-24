import { INestApplication } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import { randomUUID } from 'node:crypto';
import request from 'supertest';
import { AppModule } from '../src/app.module';
import { configureApp } from '../src/configure-app';
import { PrismaService } from '../src/prisma/prisma.service';

const INTERNAL = { 'x-internal-token': process.env.INTERNAL_API_TOKEN as string };

describe('Participation service (e2e)', () => {
  let app: INestApplication;
  let prisma: PrismaService;

  const planId = randomUUID();
  const activityA = randomUUID();
  const activityB = randomUUID();
  const memberA = randomUUID();
  const memberB = randomUUID();
  const bearer = (memberId: string) => ({ authorization: `Bearer dev:${memberId}` });

  let roundId: string;

  const provisionBody = () => ({
    operationId: randomUUID(),
    roundId,
    planId,
    optionRevision: 1,
    activityIds: [activityA, activityB],
  });

  const draftBody = (overrides: Record<string, unknown> = {}) => ({
    expectedRevision: 0,
    acknowledgedOptionRevision: 1,
    availability: [{ startAt: '2026-10-09T11:00:00+08:00', endAt: '2026-10-09T13:00:00+08:00' }],
    budget: { kind: 'CAP', capMinor: 3500 },
    activityAnswers: [
      { activityId: activityA, kind: 'RATING', rating: 4 },
      { activityId: activityB, kind: 'NO_PREFERENCE' },
    ],
    privateNote: 'prefers somewhere quiet',
    ...overrides,
  });

  beforeAll(async () => {
    const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).compile();
    app = moduleRef.createNestApplication();
    configureApp(app);
    await app.init();
    prisma = app.get(PrismaService);
  });

  afterAll(async () => {
    await app.close();
  });

  beforeEach(async () => {
    roundId = randomUUID();
  });

  afterEach(async () => {
    await prisma.responseRound.deleteMany({ where: { planId } });
  });

  describe('health', () => {
    it('reports live and ready', async () => {
      await request(app.getHttpServer()).get('/health').expect(200, { status: 'ok' });
      await request(app.getHttpServer()).get('/health/ready').expect(200, { status: 'ok' });
    });
  });

  describe('POST /internal/rounds/provision', () => {
    it('rejects callers without the internal token', async () => {
      const res = await request(app.getHttpServer())
        .post('/internal/rounds/provision')
        .send(provisionBody())
        .expect(401);
      expect(res.body.code).toBe('UNAUTHENTICATED');
      expect(res.body.requestId).toEqual(expect.any(String));
    });

    it('rejects a wrong internal token', async () => {
      await request(app.getHttpServer())
        .post('/internal/rounds/provision')
        .set('x-internal-token', 'definitely-not-the-token')
        .send(provisionBody())
        .expect(403);
    });

    it('is idempotent for the same operation and payload', async () => {
      const body = provisionBody();
      const first = await request(app.getHttpServer())
        .post('/internal/rounds/provision')
        .set(INTERNAL)
        .send(body)
        .expect(200);
      expect(first.body).toMatchObject({ roundId, state: 'COLLECTING', alreadyProvisioned: false });

      const second = await request(app.getHttpServer())
        .post('/internal/rounds/provision')
        .set(INTERNAL)
        .send({ ...body, activityIds: [activityB, activityA] }) // order must not matter
        .expect(200);
      expect(second.body).toMatchObject({ roundId, alreadyProvisioned: true });
    });

    it('rejects reuse of the round with a different operation or payload', async () => {
      const body = provisionBody();
      await request(app.getHttpServer())
        .post('/internal/rounds/provision')
        .set(INTERNAL)
        .send(body)
        .expect(200);

      const differentPayload = await request(app.getHttpServer())
        .post('/internal/rounds/provision')
        .set(INTERNAL)
        .send({ ...body, optionRevision: 2 })
        .expect(409);
      expect(differentPayload.body.code).toBe('OPERATION_CONFLICT');

      await request(app.getHttpServer())
        .post('/internal/rounds/provision')
        .set(INTERNAL)
        .send({ ...body, operationId: randomUUID() })
        .expect(409);
    });

    it('validates the body', async () => {
      const res = await request(app.getHttpServer())
        .post('/internal/rounds/provision')
        .set(INTERNAL)
        .send({ ...provisionBody(), activityIds: [] })
        .expect(400);
      expect(res.body.code).toBe('INVALID_INPUT');
      expect(res.body.fieldErrors[0].field).toBe('activityIds');
    });
  });

  describe('/rounds/:roundId/my-response', () => {
    beforeEach(async () => {
      await request(app.getHttpServer())
        .post('/internal/rounds/provision')
        .set(INTERNAL)
        .send(provisionBody())
        .expect(200);
    });

    const url = () => `/rounds/${roundId}/my-response`;

    it('requires a session', async () => {
      const res = await request(app.getHttpServer()).get(url()).expect(401);
      expect(res.body.code).toBe('UNAUTHENTICATED');
    });

    it('returns an empty draft before anything is saved', async () => {
      const res = await request(app.getHttpServer()).get(url()).set(bearer(memberA)).expect(200);
      expect(res.body).toMatchObject({
        memberId: memberA,
        status: 'DRAFT',
        revision: 0,
        budget: { kind: 'UNANSWERED', capMinor: null },
        availability: [],
        activityAnswers: [],
      });
    });

    it('saves and reads back a private draft', async () => {
      const saved = await request(app.getHttpServer())
        .put(url())
        .set(bearer(memberA))
        .send(draftBody())
        .expect(200);
      expect(saved.body.revision).toBe(1);

      const read = await request(app.getHttpServer()).get(url()).set(bearer(memberA)).expect(200);
      expect(read.body).toMatchObject({
        status: 'DRAFT',
        revision: 1,
        budget: { kind: 'CAP', capMinor: 3500 },
        privateNote: 'prefers somewhere quiet',
      });
      expect(read.body.availability).toEqual([
        { startAt: '2026-10-09T03:00:00.000Z', endAt: '2026-10-09T05:00:00.000Z' },
      ]);
      expect(read.body.activityAnswers).toHaveLength(2);
    });

    it("never shows one member another member's answers", async () => {
      await request(app.getHttpServer()).put(url()).set(bearer(memberA)).send(draftBody()).expect(200);

      const other = await request(app.getHttpServer()).get(url()).set(bearer(memberB)).expect(200);
      expect(other.body).toMatchObject({ memberId: memberB, revision: 0, activityAnswers: [] });
      expect(other.body.privateNote).toBeNull();
    });

    it('rejects stale revisions instead of overwriting', async () => {
      await request(app.getHttpServer()).put(url()).set(bearer(memberA)).send(draftBody()).expect(200);

      // A second tab still believes the draft has never been saved.
      const stale = await request(app.getHttpServer())
        .put(url())
        .set(bearer(memberA))
        .send(draftBody({ expectedRevision: 0 }))
        .expect(409);
      expect(stale.body.code).toBe('STALE_VERSION');

      const ok = await request(app.getHttpServer())
        .put(url())
        .set(bearer(memberA))
        .send(draftBody({ expectedRevision: 1, budget: { kind: 'UNLIMITED' } }))
        .expect(200);
      expect(ok.body).toMatchObject({ revision: 2, budget: { kind: 'UNLIMITED', capMinor: null } });
    });

    it('serialises concurrent first saves: exactly one wins', async () => {
      const results = await Promise.all(
        [1, 2, 3, 4].map(() =>
          request(app.getHttpServer()).put(url()).set(bearer(memberA)).send(draftBody()),
        ),
      );
      const statuses = results.map((r) => r.status).sort();
      expect(statuses.filter((s) => s === 200)).toHaveLength(1);
      expect(statuses.filter((s) => s === 409)).toHaveLength(3);
    });

    it('rejects writes once the round is frozen', async () => {
      await prisma.responseRound.update({ where: { id: roundId }, data: { state: 'FROZEN' } });
      const res = await request(app.getHttpServer())
        .put(url())
        .set(bearer(memberA))
        .send(draftBody())
        .expect(409);
      expect(res.body.code).toBe('ROUND_CLOSED');
    });

    it('rejects a form built from an older option revision', async () => {
      const res = await request(app.getHttpServer())
        .put(url())
        .set(bearer(memberA))
        .send(draftBody({ acknowledgedOptionRevision: 2 }))
        .expect(409);
      expect(res.body.code).toBe('STALE_VERSION');
    });

    it('returns field errors for invalid drafts and extra properties', async () => {
      const invalid = await request(app.getHttpServer())
        .put(url())
        .set(bearer(memberA))
        .send(
          draftBody({
            budget: { kind: 'CAP' },
            activityAnswers: [{ activityId: activityA, kind: 'RATING' }],
          }),
        )
        .expect(400);
      expect(invalid.body.code).toBe('INVALID_INPUT');
      expect(invalid.body.fieldErrors.map((e: { field: string }) => e.field)).toEqual(
        expect.arrayContaining(['budget.capMinor', 'activityAnswers.0.rating']),
      );

      await request(app.getHttpServer())
        .put(url())
        .set(bearer(memberA))
        .send({ ...draftBody(), memberId: memberB }) // cannot target another member
        .expect(400);
    });

    it('submits a complete draft and rejects an incomplete one', async () => {
      await request(app.getHttpServer())
        .post(`${url()}/submit`)
        .set(bearer(memberA))
        .send({ expectedRevision: 0 })
        .expect(400);

      const saved = await request(app.getHttpServer())
        .put(url())
        .set(bearer(memberA))
        .send(draftBody())
        .expect(200);

      const submitted = await request(app.getHttpServer())
        .post(`${url()}/submit`)
        .set(bearer(memberA))
        .send({ expectedRevision: saved.body.revision })
        .expect(200);
      expect(submitted.body.status).toBe('SUBMITTED');
    });
  });

  describe('freeze and Decision snapshot', () => {
    beforeEach(async () => {
      await request(app.getHttpServer())
        .post('/internal/rounds/provision')
        .set(INTERNAL)
        .send(provisionBody())
        .expect(200);
    });

    it('freezes the round, exposes a Decision snapshot, and closes writes', async () => {
      await request(app.getHttpServer())
        .put(`/rounds/${roundId}/my-response`)
        .set(bearer(memberA))
        .send(draftBody())
        .expect(200);
      await request(app.getHttpServer())
        .post(`/rounds/${roundId}/my-response/submit`)
        .set(bearer(memberA))
        .send({ expectedRevision: 1 })
        .expect(200);

      const frozen = await request(app.getHttpServer())
        .post('/internal/rounds/freeze')
        .set(INTERNAL)
        .send({ operationId: randomUUID(), roundId, memberIds: [memberA, memberB] })
        .expect(200);
      expect(frozen.body.state).toBe('FROZEN');
      expect(frozen.body.snapshot.participants).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ participant_id: memberA, response_status: 'complete' }),
          expect.objectContaining({ participant_id: memberB, response_status: 'incomplete' }),
        ]),
      );
      expect(JSON.stringify(frozen.body.snapshot)).not.toContain('prefers somewhere quiet');

      const snapshot = await request(app.getHttpServer())
        .get(`/internal/rounds/${roundId}/response-snapshot`)
        .set(INTERNAL)
        .expect(200);
      expect(snapshot.body.snapshot_id).toBe(frozen.body.snapshotId);

      const closed = await request(app.getHttpServer())
        .put(`/rounds/${roundId}/my-response`)
        .set(bearer(memberA))
        .send(draftBody({ expectedRevision: 1 }))
        .expect(409);
      expect(closed.body.code).toBe('ROUND_CLOSED');
    });
  });
});
