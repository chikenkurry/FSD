# Participation service: API for other teams

Owner: pair B (M3 backend). Status: **R01 implemented**. Anything marked *Planned* is not built yet and may change.

## Live documentation (Swagger / OpenAPI)

Run the service, then open:

| What | URL |
| --- | --- |
| Swagger UI (try requests in the browser) | `http://localhost:3000/docs` |
| Raw OpenAPI 3 JSON (import into Postman/Insomnia, generate clients) | `http://localhost:3000/docs-json` |

Swagger lists request bodies and validation rules. It does not describe response shapes, so use the examples below for those. Once F02 publishes the shared contract examples in the team's `contracts/`, copy the request and response samples from this file there.

## Who calls what

| Caller | Endpoint | Public via gateway? |
| --- | --- | --- |
| Planning (server to server) | `POST /internal/rounds/provision` | **No.** Internal only |
| Frontend (member's browser) | `GET` and `PUT /rounds/{roundId}/my-response` | Yes |
| Gateway / orchestrator | `GET /health`, `GET /health/ready` | Health checks only |
| Participation calls **Planning** | `POST {PLANNING_BASE_URL}/internal/sessions/authorise` | Internal. Planning must build this (below) |
| Decision | *Planned (R02):* response snapshot read | Internal |

Gateway rule: route only `/rounds/*` to this service. **Never route `/internal/*` or `/docs*` publicly.**

## Conventions

- JSON over HTTP. Dates are ISO-8601 with an explicit offset (`2026-10-09T19:00:00+08:00` or `...Z`). Stored and returned in UTC.
- IDs are UUIDs issued by Planning. Money is integer minor units (SGD cents): `3500` = S$35.00.
- Every response carries `x-request-id`. Send your own `x-request-id` (8-64 chars of `A-Z a-z 0-9 _ -`) to correlate logs.
- Bodies are limited to 100 kB. Unknown properties are rejected with 400.

### Authentication

| Route family | Credential |
| --- | --- |
| `/internal/*` | Header `x-internal-token: <shared secret>` (set `INTERNAL_API_TOKEN` identically on callers) |
| `/rounds/*` | The member's session: `Authorization: Bearer <session token>` or the session cookie (`SESSION_COOKIE_NAME`, default `what2do_session`). Participation never trusts a member ID from the client; it asks Planning who the session belongs to |
| Local development only | `AUTH_MODE=dev`: `Authorization: Bearer dev:<member-uuid>`. Refused in production |

### Error format (`ApiErrorV1`)

Every error has this shape:

```json
{
  "code": "STALE_VERSION",
  "message": "The resource changed since you last loaded it",
  "retryable": false,
  "requestId": "3f2c9a6e-1b0d-4c1e-9f55-0a7d2c4b8e11",
  "fieldErrors": [{ "field": "budget.capMinor", "message": "capMinor is required when kind is CAP" }]
}
```

`fieldErrors` appears only for `INVALID_INPUT`.

| HTTP | `code` | Meaning | Retry? |
| --- | --- | --- | --- |
| 400 | `INVALID_INPUT` | Body or ID failed validation. See `fieldErrors` | Fix the request |
| 401 | `UNAUTHENTICATED` | Missing or unknown credential | Re-authenticate |
| 403 | `FORBIDDEN` | Valid session but not allowed for this round or plan | No |
| 404 | `NOT_FOUND` | Round not provisioned here | After provisioning |
| 409 | `STALE_VERSION` | Your `expectedRevision` or `acknowledgedOptionRevision` is out of date | Reload, then resend |
| 409 | `ROUND_CLOSED` | Round is frozen; no more writes | No |
| 409 | `OPERATION_CONFLICT` | Provision `operationId`/payload reused inconsistently | No: fix the caller |
| 429 | `RATE_LIMITED` | Reserved | Back off |
| 503 | `UPSTREAM_UNAVAILABLE` | Planning (authorisation) or the database is unavailable. Fails closed | Yes, with backoff |
| 500 | `INTERNAL` | Unexpected | Yes, then report the `requestId` |

---

## 1. Provision a round (Planning to Participation)

`POST /internal/rounds/provision`, header `x-internal-token`.

Called when the organiser publishes (Planning state OPENING). Planning marks the round COLLECTING only after this returns 200.

```json
{
  "operationId": "6b1d0f0e-2c34-4a57-9d1e-3c7a6f2e9a10",
  "roundId": "0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33",
  "planId": "c1a2b3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
  "optionRevision": 1,
  "activityIds": [
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222"
  ]
}
```

| Field | Rule |
| --- | --- |
| `operationId` | Idempotency key. **Reuse the same value on retries** |
| `roundId`, `planId` | Planning's IDs |
| `optionRevision` | Integer >= 1: the published option revision members will answer against |
| `activityIds` | 1-8 unique UUIDs: the only activities members may answer |

Response `200`:

```json
{
  "roundId": "0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33",
  "planId": "c1a2b3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
  "optionRevision": 1,
  "state": "COLLECTING",
  "alreadyProvisioned": false
}
```

Idempotency: repeating the identical call (activity order does not matter) returns `200` with `alreadyProvisioned: true`. The same round or `operationId` with a *different* payload returns `409 OPERATION_CONFLICT`. A timeout is safe to retry. A new round (price/time/activity change) needs a new `roundId` and `optionRevision`.

*Planned (R04):* the same call will accept the previous round's ID so answers can be copied across as drafts.

## 2. Read my response (frontend)

`GET /rounds/{roundId}/my-response`, member session. Always returns the caller's own response.

```json
{
  "roundId": "0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33",
  "memberId": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  "status": "DRAFT",
  "revision": 1,
  "acknowledgedOptionRevision": 1,
  "availability": [
    { "startAt": "2026-10-09T11:00:00.000Z", "endAt": "2026-10-09T13:00:00.000Z" }
  ],
  "budget": { "kind": "CAP", "capMinor": 3500 },
  "activityAnswers": [
    { "activityId": "11111111-1111-4111-8111-111111111111", "kind": "RATING", "rating": 4 },
    { "activityId": "22222222-2222-4222-8222-222222222222", "kind": "NO_PREFERENCE", "rating": null }
  ],
  "privateNote": "quiet please",
  "updatedAt": "2026-10-06T00:20:00.000Z",
  "round": { "optionRevision": 1, "state": "COLLECTING" }
}
```

If the member has never saved: `revision: 0`, `status: "DRAFT"`, empty lists, `budget: { "kind": "UNANSWERED", "capMinor": null }`, `updatedAt: null`.

## 3. Save my response (frontend)

`PUT /rounds/{roundId}/my-response`, member session. Replaces the whole draft. Partial drafts are allowed; completeness is checked at submission (*Planned, R02*).

```json
{
  "expectedRevision": 0,
  "acknowledgedOptionRevision": 1,
  "availability": [
    { "startAt": "2026-10-09T19:00:00+08:00", "endAt": "2026-10-09T21:00:00+08:00" }
  ],
  "budget": { "kind": "CAP", "capMinor": 3500 },
  "activityAnswers": [
    { "activityId": "11111111-1111-4111-8111-111111111111", "kind": "RATING", "rating": 4 },
    { "activityId": "22222222-2222-4222-8222-222222222222", "kind": "NO_PREFERENCE" }
  ],
  "privateNote": "optional, never used by the algorithm, never shared"
}
```

Returns the saved response (same shape as section 2) with `revision` incremented.

| Field | Rules |
| --- | --- |
| `expectedRevision` | The `revision` you last loaded (`0` if never saved). Mismatch returns `409 STALE_VERSION`: reload and merge |
| `acknowledgedOptionRevision` | The `round.optionRevision` the form was rendered from. Must equal the current one |
| `availability[]` | Up to 500 intervals the member **is** available. Each `endAt > startAt`, both on a 30-minute boundary, no overlaps. Unmarked time means unavailable |
| `budget.kind` | `UNANSWERED` (not answered; neither 0 nor unlimited), `CAP`, `UNLIMITED` (explicit "no limit") |
| `budget.capMinor` | Integer 0-100,000,000. **Required with `CAP`, forbidden otherwise.** `0` means free only |
| `activityAnswers[]` | At most one per activity, only activities of this round. A missing activity means unanswered |
| `activityAnswers[].kind` | `RATING` (needs `rating` 0-4: 0 strongly dislike, 1 dislike, 2 neutral, 3 like, 4 love), `NO_PREFERENCE` (counts as neutral), `CANNOT_JOIN` (hard exclusion), `NEEDS_INFO` (candidate stays unresolved). `rating` is forbidden unless `kind` is `RATING` |
| `privateNote` | Optional, up to 1000 chars or `null` |

Two saves racing from the same member: one wins, the other gets `409 STALE_VERSION`.

## 4. Health

- `GET /health`: liveness, `{ "status": "ok" }`.
- `GET /health/ready`: readiness, checks the database. `503 UPSTREAM_UNAVAILABLE` if it is down. Use this for load balancer checks.

---

## What other teams must provide to Participation

### Planning: session authorisation (needed before production auth works)

Participation calls this on every member request and **fails closed** (503) if it cannot get an answer. *Provisional: M1 and M3 to agree under F05.*

```
POST {PLANNING_BASE_URL}/internal/sessions/authorise
x-internal-token: <shared secret>

{ "sessionToken": "<opaque token from the cookie/header>", "roundId": "<uuid>" }
```

`200`:

```json
{ "memberId": "<uuid>", "planId": "<uuid>", "roundId": "<same roundId>", "canRespond": true }
```

`401` unknown/revoked session, `403`/`404` not an approved member of that round's plan. Participation compares `planId` with the provisioned round and rejects a mismatch.

### Planning: lifecycle calls

- Publish: call provision (section 1) with a persisted `operationId`; mark COLLECTING only after `200`.
- Close/freeze, snapshots, RSVP: *Planned (R02, R05).* Participation will expose an internal freeze (idempotent per `operationId`, writes before the freeze are included, writes after are rejected with `ROUND_CLOSED`) and an immutable response snapshot.

### Decision: data it will read (*Planned, R02*)

An internal read of an immutable `ResponseSnapshotV1` for a frozen round: per member, the availability intervals, budget (`kind` + cap), per-activity answers (with `NO_PREFERENCE` already mapped to neutral), excluding private notes and any identity or session data. The exact shape will be published under F02 before Decision depends on it. Until then, build against fixtures that follow the field meanings in section 3.

## Quick local test

```bash
# 1. Open a round (as Planning)
curl -X POST http://localhost:3000/internal/rounds/provision \
  -H "content-type: application/json" -H "x-internal-token: local-dev-internal-token-change-me" \
  -d '{"operationId":"6b1d0f0e-2c34-4a57-9d1e-3c7a6f2e9a10","roundId":"0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33","planId":"c1a2b3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d","optionRevision":1,"activityIds":["11111111-1111-4111-8111-111111111111"]}'

# 2. Read my (empty) response as a dev member
curl http://localhost:3000/rounds/0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33/my-response \
  -H "authorization: Bearer dev:dddddddd-dddd-4ddd-8ddd-dddddddddddd"
```

(On Windows `cmd`, use the Swagger UI at `/docs` or Postman instead of these curl lines, since quoting JSON differs.)
