# Participation service

Part of What2Do. Owns what each member answers: response drafts, availability, private budgets,
question answers, activity answers, immutable response snapshots, freeze and versioned RSVPs.
Planning owns membership and sessions; Decision never writes here.
The connected stack and form lifecycle are documented in [Service integration](../integration/README.md).

NestJS + TypeScript, PostgreSQL via Prisma. One repo per service. Requires Node 22

## Status

| Ticket | State |
| --- | --- |
| R01 provision a round, save and read a private draft | Implemented |
| R02 submit, immutable snapshot, freeze | Implemented |
| Published question forms (`questions`, `answers[]`, importance, requirement confirmations, date polls, option ratings) | Implemented |
| Published roster (`publication`) and final-roster (`close`) freeze, early close, require-complete freeze | Implemented |
| Copy an earlier round's answers into a new draft | Implemented |
| Internal per-member snapshot preview | Implemented |
| Versioned RSVP against Planning's current selection | Implemented |

## How a round works
 
1. **Provision.** Planning calls `POST /internal/rounds/provision`. The round is `COLLECTING`.
2. **Collect.** Members read, save, submit (or copy from an earlier round) through `/rounds/:roundId/my-response`.
   Planning may poll `progress` and call `preview-snapshot` for one member.
3. **Freeze.** Planning calls `POST /internal/rounds/freeze` with the final roster. The round becomes
   `FROZEN`, the snapshot is stored, and later member writes return `409 ROUND_CLOSED`.
4. **Decide.** Decision reads `GET /internal/rounds/:roundId/response-snapshot`.
5. **RSVP.** Members answer `GOING`, `MAYBE` or `DECLINED` for Planning's current selection.
A round is either legacy (no `questions`: members give a budget, availability and an answer per activity)
or a question form (`questions` provisioned: completeness is decided by the required questions).

## Run it locally

Requires Node 22 and Docker.

```bash
cp .env_example .env
npm install
docker compose up -d db
npx prisma migrate dev        # applies migrations to the local database
npm run start:dev             # http://localhost:3000, OpenAPI at /docs
```

Committed migrations include question answers, published membership, currency precision
and a constraint requiring non-null ratings for `RATING` answers. Production applies
them with `prisma migrate deploy`; the Docker image runs that before startup.

## Configuration
 
Read once at startup by `AppConfig`; invalid configuration stops the process.
 
| Variable | Default | Rules |
| --- | --- | --- |
| `DATABASE_URL` | none | PostgreSQL connection string used by Prisma |
| `PORT` | `3000` | Positive integer |
| `NODE_ENV` | `development` | `production` refuses `AUTH_MODE=dev` |
| `AUTH_MODE` | `planning` | `planning` (real) or `dev` (local and tests only) |
| `INTERNAL_API_TOKEN` | none | Required, at least 16 characters. Shared secret for `/internal/*` and for calls to Planning |
| `PLANNING_BASE_URL` | none | Required when `AUTH_MODE=planning`; trailing slashes are removed. Also used by RSVP saves (see below) |
| `SESSION_COOKIE_NAME` | `what2do_session` | Cookie read when no bearer token is sent |

## Tests

```bash
npm run typecheck
npm test              # unit tests, no database needed
npm run test:e2e      # needs the migrated local database; deletes only rows of its own random plan
```

## Endpoints
Public routes go through the gateway; `/internal/*` and `/docs*` must not.

| Method and path | Caller | Purpose |
| --- | --- | --- |
| `GET /health`, `GET /health/ready` | gateway, orchestrator | liveness; readiness (checks the database) |
| `POST /internal/rounds/provision` | Planning | idempotent: create the round and open it for responses |
| `POST /internal/rounds/freeze` | Planning | idempotent: close writes and store the response snapshot |
| `GET /internal/rounds/:roundId/response-snapshot` | Decision | the stored `response-snapshot-v2` (404 until frozen) |
| `GET /internal/rounds/:roundId/progress` | Planning | submitted and draft counts, per-member `status` and `decisionStatus` |
| `GET /internal/rounds/:roundId/members/:memberId/preview-snapshot` | Planning | one member's snapshot as it would be frozen now (not stored); 409 once frozen |
| `GET /rounds/:roundId/my-response` | member | own draft (revision 0 and empty if never saved) |
| `PUT /rounds/:roundId/my-response` | member | replace own draft; send back the `revision` you loaded as `expectedRevision` |
| `POST /rounds/:roundId/my-response/submit` | member | mark a complete draft submitted |
| `POST /rounds/:roundId/my-response/copy` | member | copy answers from an earlier round of the same plan into a new draft |
| `GET /rounds/:roundId/my-rsvp` | member | own RSVP plus going/maybe/declined counts |
| `PUT /rounds/:roundId/my-rsvp` | member | save own RSVP for the current selection version |

`/internal/*` needs the `x-internal-token` header. Bodies are limited to 100 kB and unknown properties
are rejected with 400. Full payloads, rules and error cases are in [docs/API.md](docs/API.md).
With the service running, Swagger UI is at `/docs` and the OpenAPI JSON at `/docs-json`.

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

## Authentication and authorisation
 
- **Members** (`/rounds/*`). `MemberSessionGuard` checks `:roundId` is a UUID (lower-cased), reads the
  token from `Authorization: Bearer ...` or, if absent, the session cookie, and asks `SessionAuthoriser`
  who it belongs to. The member is always derived from the credential, never from the URL or body.
  - `PlanningSessionAuthoriser` (`AUTH_MODE=planning`) calls Planning
    `POST {PLANNING_BASE_URL}/internal/sessions/authorise` (3 s timeout). `401` maps to `UNAUTHENTICATED`,
    `403`/`404` to `FORBIDDEN`, any other failure or timeout to `503 UPSTREAM_UNAVAILABLE` (fails closed).
    A `200` is accepted only if `memberId` and `planId` are UUIDs, `roundId` equals the requested (lower-case)
    round and `canRespond` is `true`; otherwise `FORBIDDEN`.
  - `DevSessionAuthoriser` (`AUTH_MODE=dev`) trusts `dev:<member-uuid>` and uses the round's own `planId`;
    an unknown round is `FORBIDDEN`.
- **Service calls** (`/internal/*`). `InternalTokenGuard` compares `x-internal-token` in constant time
  (SHA-256 of both sides). Missing is `401 UNAUTHENTICATED`, wrong is `403 FORBIDDEN`.
- **Round access** (`ResponsesService.requireRound`). The round must exist (`404`) and belong to the
  session's plan (`403`). For a `publication` round, or any frozen round, a non-empty published `memberIds`
  list must contain the member (`403`). A `close` round that is still collecting accepts any authorised
  member of the plan; the final roster is fixed at freeze.
- **Cookies.** The guard accepts the session cookie, but the integration uses bearer tokens.
  Cookie-authenticated writes need the gateway's CSRF policy before that transport is used in production.

## Rounds and member responses
 
### Provisioning
 
`operationId`, `roundId`, `planId`, `optionRevision` (>= 1) and 1-8 `activityIds` are required. Optional:
`rosterPolicy` (`publication` default, or `close`), `memberIds` (1-30), `optionSnapshotId`, `questions`
(up to 100), `currency` (3 capital letters, default `SGD`) and `minorDigits` (0-9, default `2`).
A `close` round requires `optionSnapshotId`. Identifiers must be unique (case-insensitive).
Replays are idempotent (see [Idempotency](#idempotency)).
 
### Question forms
 
Each question is `{ questionId, required, answerFormat, choices? }` with `answerFormat` one of `text`,
`choice`, `multi_choice`, `number`, `boolean`, `date_intervals`, `option_rating`, `date_poll`.
Members answer in `answers[]` (up to 100): `{ question_id, value, importance?, confirmed_requirement?,
confirmed_requirements?, reviewed_revision? }`. `importance` is `low`, `normal` or `high`. Rules:
 
- each answer must target a published question, at most once, and its JSON must be at most 16,000 characters;
- the value must fit the format: `text` string, `number` finite number, `boolean`, `multi_choice` and
  `date_intervals` arrays, `choice`/`multi_choice` selections among `choices` (items may be `{ choice_id }`),
  `date_poll` an object of up to 31 published dates mapped to `yes`/`maybe`/`no`, `option_rating` an object of
  up to 20 option ids mapped to whole numbers 0-4;
- confirmation records are stored as given and only checked to be valid JSON, except in `close` rounds, where a
  confirmation is accepted only if the stored answer has the same value and `reviewed_revision` equals the
  `expectedRevision` of the save (save the answer, preview it, then confirm), otherwise `409 STALE_VERSION`;
- if the round has an `optionSnapshotId`, `activityAnswers` of kind `RATING` or `NO_PREFERENCE` are rejected;
  preferences come from question answers instead.
### Drafts, revisions and submit
 
- A save replaces the whole draft. `expectedRevision` must equal the stored `revision` (0 for a first save),
  and `acknowledgedOptionRevision` must equal the round's `optionRevision`. Each save and each submit
  increases `revision`; saving after a submit returns the response to `DRAFT`.
- Availability: up to 500 intervals, `endAt` after `startAt`, both on the 30-minute grid, no overlaps, ISO-8601
  with an explicit offset. Unmarked time means unavailable.
- Budget: `UNANSWERED`, `CAP` (`capMinor` integer 0-100,000,000, required with `CAP`, forbidden otherwise) or
  `UNLIMITED`. A cap of `0` means free only.
- Activity answers: at most one per activity of the round; `RATING` needs `rating` 0-4, other kinds forbid it.
- `privateNote` (up to 1000 characters) is never shared and never appears in a snapshot.
- Submit needs a complete draft. For a question form: every required question has a non-empty answer.
  For a legacy round: budget is not `UNANSWERED` and every activity has an answer. A draft saved against an old
  `acknowledgedOptionRevision` cannot be submitted (`STALE_VERSION`). Retrying a submit with the pre-submit
  revision returns the submitted response.
### Copy
 
`POST .../my-response/copy` with `{ sourceRoundId }` creates a revision-1 draft from the caller's response in
an earlier round of the same plan (the target's `optionRevision` must be higher). It keeps availability, private
note, activity answers for activities still in the round, and `question_id`/`value` of answers for questions still
published (importance and confirmations are dropped). The budget is kept only if currency and `minorDigits` match,
otherwise it becomes `UNANSWERED`. The copy records the source's option revision, so the member must save against
the current revision before submitting. It never overwrites an existing draft (`409 OPERATION_CONFLICT`).
 
## Freeze and snapshot
 
`POST /internal/rounds/freeze` takes `operationId`, `roundId`, `memberIds` (1-30, the final roster) and optional
`requireComplete`, `countRespondedOnly`, `optionSnapshotId`, `optionRevision`.
 
- Under an exclusive lock on the round row, it builds a `response-snapshot-v2`, stores it with the roster, and
  sets the round to `FROZEN`.
- `publication` rounds: a non-empty published roster must equal `memberIds`. `close` rounds: `optionSnapshotId`
  and `optionRevision` are required, and the roster is whatever Planning sends. A given `optionRevision` must
  match the round's.
- `requireComplete` fails if any listed member is not `complete`. `countRespondedOnly` (early close) freezes with
  whoever has a complete, current submission and fails if nobody does; others stay on the roster but get
  `is_required_for_decision: false`. A failed attempt returns `409 RESPONSES_INCOMPLETE`, leaves the round
  `COLLECTING`, and that `operationId` stays rejected on retry; use a new `operationId` to try again.
- Snapshots over 1.5 MB are refused with `400 INVALID_INPUT`.
Snapshot content (private notes are omitted): `schema_version`, `option_snapshot_id`, `currency`,
`minor_digits`, `snapshot_id`, `round_id`, `plan_id`, `option_revision`, `created_at`, then per member sorted by id:
`participants` (`response_status` `complete`/`incomplete`/`stale`, `is_required_for_decision`, and `answers`
for question forms), `constraints` (availability, budget `limited`/`unlimited`/`missing`, `activity_flags` for
`cannot_join`/`needs_information`, empty `required_attributes` and `candidate_flags`) and `preferences`
(`RATING` as given, `NO_PREFERENCE` as rating 2). Status is `stale` when the member acknowledged an older option
revision, `complete` when the answers are complete and `SUBMITTED`, otherwise `incomplete`.
 
## RSVP
 
`GET` returns the caller's RSVP (`revision: 0`, `status: null` if none) with a `summary` of all RSVPs for the
round. `PUT` takes `{ selectionVersion, expectedRevision, status }`. Before writing, the service reads
`GET {PLANNING_BASE_URL}/internal/rounds/:roundId/selection` (3 s timeout) and requires `plan_id` to match the
session, `round_id` to match the route, `selection_version` to equal the request and `is_current` to be `true`
(`409 STALE_VERSION` otherwise; a `404`/`409` from Planning is `409 OPERATION_CONFLICT`; other failures
are `503`). The write is revision-checked and idempotent for an exact retry. An RSVP stays attached to the
`selectionVersion` it was created for. RSVP saves need `PLANNING_BASE_URL` even when `AUTH_MODE=dev`.
 
## Idempotency
 
- **Provision**: same `operationId` and payload returns `alreadyProvisioned: true` (activity, member and question
  order do not matter). Same round or `operationId` with a different payload is `409 OPERATION_CONFLICT`.
- **Freeze**: same `operationId` and request (roster order and UUID case do not matter) returns
  `alreadyFrozen: true` with the same `snapshotId`; anything different for a frozen round is `409 OPERATION_CONFLICT`.
- **Member writes**: protected by `revision`, not by operation ids.
## Errors
 
Every error is `ApiErrorV1`: `{ code, message, retryable, requestId, fieldErrors? }`.
Codes: `UNAUTHENTICATED` (401), `FORBIDDEN` (403), `NOT_FOUND` (404), `INVALID_INPUT` (400, also oversized
bodies), `STALE_VERSION`, `ROUND_CLOSED`, `RESPONSES_INCOMPLETE`, `OPERATION_CONFLICT` (all 409),
`RATE_LIMITED` (429, reserved: nothing rate-limits yet), `UPSTREAM_UNAVAILABLE` (503, retryable),
`INTERNAL` (500, retryable). Unexpected errors and framework errors return generic messages, and request bodies
are never logged. Send or read `x-request-id` to correlate logs.

## Code structure
 
Dependencies point inward: controllers call services, services call repository *interfaces*, and only
`src/prisma/` knows about Prisma.
 
| Folder | Responsibility |
| --- | --- |
| `src/rounds` | Internal controller, `RoundsService` (provision, freeze, snapshot, progress), DTOs, payload hashes, `RoundRepository` port |
| `src/responses` | Member and internal-preview controllers, `ResponsesService` (read, save, submit, copy, preview), DTOs, pure rules (`response-rules.ts`, `question-answer-rules.ts`, `response-completeness.ts`), snapshot mapping (`decision-snapshot.ts`), `ResponseRepository` port |
| `src/rsvps` | RSVP controller and service (uses Prisma directly and calls Planning for the selection) |
| `src/prisma` | The persistence adapter: `PrismaService` and the Prisma implementations of the repository ports |
| `src/auth` | `SessionAuthoriser` port with dev and Planning implementations, `MemberSessionGuard`, `InternalTokenGuard` |
| `src/health` | Liveness and readiness |
| `src/common`, `src/config` | Error format and filter, request id, validation helpers, environment configuration |
| `src/testing` | In-memory repository fakes and fixtures for unit tests (excluded from the build) |
 
Testing layers: pure rules and services are unit tested against the in-memory fakes (no database);
`test/*.e2e-spec.ts` exercises the real HTTP stack, Prisma and Postgres, including the concurrency cases.

## Design notes

- **Concurrency.** Saves, submits, copies and previews lock the round row `FOR SHARE`, so they run together;
  freeze locks it `FOR UPDATE`, waits for in-flight writes and then blocks later ones, which see `FROZEN`.
  A per-response `revision` check stops two tabs overwriting each other, and the unique
  `(round_id, member_id)` key settles racing first saves. RSVP saves use their own revision check.
- **Money** is integer minor units with currency and precision frozen at provisioning. `UNANSWERED`,
  `UNLIMITED` and a cap of `0` are three different things.
- **Time** is a timestamp with an explicit offset, stored and returned in UTC, on the 30-minute grid.
- **Fail closed.** If Planning cannot be reached or answers unexpectedly, member requests get 503, never access.
- **Privacy.** Members only ever reach their own response; progress exposes counts and status only; snapshots
  omit private notes.

## Open contract questions

Planning now implements session authorisation and provisions the question schema,
published roster and snapshot identity. Its freeze call sends those same user IDs.
The integration uses bearer tokens. Cookie-authenticated writes still need the
team's gateway CSRF policy before using that transport in production.
