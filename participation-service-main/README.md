# Participation service

Part of What2Do. Owns what each member answers: response drafts, availability, private budgets,
activity answers, (later) immutable response snapshots, freeze and RSVPs.
Planning owns membership and sessions; Decision never writes here.

NestJS + TypeScript, PostgreSQL via Prisma. One repo per service.

## Status

| Ticket | State |
| --- | --- |
| R01 provision a round, save and read a private draft | Implemented (this scaffold) |
| R02 submit, immutable snapshot, freeze | Not started. The save path already takes `FOR SHARE` on the round row so freeze can take `FOR UPDATE` on the same row |
| R03-R06 | Not started |

## Run it locally

Requires Node 22 and Docker.

```bash
cp .env.example .env
npm install
docker compose up -d db
npx prisma migrate dev        # applies migrations to the local database
npm run start:dev             # http://localhost:3000, OpenAPI at /docs
```

## First-time setup: create the migrations

The repo ships `prisma/schema.prisma` but no migrations yet. Generate them once, then commit them:

```bash
npx prisma migrate dev --name init
npx prisma migrate dev --create-only --name check_constraints
# paste the contents of prisma/check_constraints.sql into the new migration.sql, save, then:
npx prisma migrate dev
```

Also commit `package-lock.json` (CI and the Dockerfile use `npm ci`).

## Tests

```bash
npm run typecheck
npm test              # unit tests, no database needed
npm run test:e2e      # needs the migrated local database; deletes only rows of its own random plan
```

## Endpoints

| Method and path | Caller | Purpose |
| --- | --- | --- |
| `GET /health`, `GET /health/ready` | gateway, orchestrator | liveness, readiness (checks the database) |
| `POST /internal/rounds/provision` | Planning only | idempotent: create the round, open for responses |
| `GET /rounds/:roundId/my-response` | member | own draft (revision 0 and empty if never saved) |
| `PUT /rounds/:roundId/my-response` | member | replace own draft; send back the `revision` you loaded as `expectedRevision` |

`/internal/*` needs the `x-internal-token` header and must not be routed through the public gateway.
Errors follow `ApiErrorV1`: `{ code, message, retryable, requestId, fieldErrors? }`.

Example save:

```json
{
  "expectedRevision": 0,
  "acknowledgedOptionRevision": 1,
  "availability": [{ "startAt": "2026-10-09T19:00:00+08:00", "endAt": "2026-10-09T21:00:00+08:00" }],
  "budget": { "kind": "CAP", "capMinor": 3500 },
  "activityAnswers": [
    { "activityId": "<uuid>", "kind": "RATING", "rating": 4 },
    { "activityId": "<uuid>", "kind": "NO_PREFERENCE" }
  ],
  "privateNote": "optional, never used by the algorithm"
}
```

Locally (`AUTH_MODE=dev`) authenticate with `Authorization: Bearer dev:<member-uuid>`.

## For other teams

See [docs/API.md](docs/API.md) for endpoints, payloads, errors, idempotency rules and what Planning/Decision must provide.
With the service running, Swagger UI is at `/docs` and the OpenAPI JSON at `/docs-json`.

## Code structure

Dependencies point inward: controllers call services, services call repository *interfaces*, and only
`src/prisma/` knows about Prisma.

| Folder | Responsibility |
| --- | --- |
| `src/rounds`, `src/responses` | Controllers (thin HTTP), services (business rules), DTOs, pure rules (`response-rules.ts`), repository interfaces |
| `src/prisma` | The only persistence adapter: `PrismaService` plus the Prisma implementations of the repository interfaces |
| `src/auth` | `SessionAuthoriser` port with dev and Planning implementations, plus the two guards |
| `src/common`, `src/config` | Error format, validation helpers, environment configuration |
| `src/testing` | In-memory repository fakes and fixtures for unit tests (excluded from the build) |

Testing layers: pure rules and services are unit tested against the in-memory fakes (no database);
`test/*.e2e-spec.ts` exercises the real HTTP stack, Prisma and Postgres, including the concurrency cases.

## Design notes

- **Authorisation.** The member comes from the session credential, never from the URL or body.
  `SessionAuthoriser` is the seam: `DevSessionAuthoriser` for local work (refused when
  `NODE_ENV=production`), `PlanningSessionAuthoriser` for real use. It fails closed with 503 when
  Planning cannot be reached.
- **Concurrency.** Saves lock the round row `FOR SHARE`; a per-response `revision` check stops two
  tabs overwriting each other; the unique `(round_id, member_id)` key settles racing first saves.
- **Money** is integer minor units (SGD cents). `UNANSWERED`, `UNLIMITED` and a cap of `0` are three different things.
- **Time** is a timestamp with an explicit offset, on the 30-minute grid. Unmarked time means unavailable.

## Open contract questions

1. Planning's session-authorise endpoint (shape in `planning-session-authoriser.ts`) needs agreeing with M1 under F05.
2. Align `ApiErrorV1` and `MemberResponseV1` with the shared examples once F02 publishes them.
3. CSRF protection for cookie-authenticated writes: decide whether the gateway or this service enforces it.
4. Whether provision carries the form schema, or only activity IDs as in this scaffold.
