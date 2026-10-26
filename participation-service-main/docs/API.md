# Participation service: API for other teams

Owner: pair B (M3 backend). Status: provisioning, member drafts, submit, copy, freeze, snapshots,
progress, preview and RSVP are all **implemented**. This file describes the service as built.

## Live documentation (Swagger / OpenAPI)

Run the service, then open:

| What | URL |
| --- | --- |
| Swagger UI (try requests in the browser) | `http://localhost:3000/docs` |
| Raw OpenAPI 3 JSON (import into Postman/Insomnia, generate clients) | `http://localhost:3000/docs-json` |

Swagger lists request bodies and validation rules. Use the examples below for response shapes. Once F02
publishes the shared contract examples in the team's `contracts/`, copy the request and response samples there.

## Who calls what

| Caller | Endpoint | Public via gateway? |
| --- | --- | --- |
| Planning (server to server) | `POST /internal/rounds/provision`, `POST /internal/rounds/freeze`, `GET /internal/rounds/{roundId}/progress`, `GET /internal/rounds/{roundId}/members/{memberId}/preview-snapshot` | **No.** Internal only |
| Decision | `GET /internal/rounds/{roundId}/response-snapshot` | **No.** Internal only |
| Frontend (member's browser) | `GET`/`PUT /rounds/{roundId}/my-response`, `POST .../my-response/submit`, `POST .../my-response/copy`, `GET`/`PUT /rounds/{roundId}/my-rsvp` | Yes |
| Gateway / orchestrator | `GET /health`, `GET /health/ready` | Health checks only |
| Participation calls **Planning** | `POST {PLANNING_BASE_URL}/internal/sessions/authorise`, `GET {PLANNING_BASE_URL}/internal/rounds/{roundId}/selection` | Internal. Planning must provide both (below) |

Gateway rule: route only `/rounds/*` to this service. **Never route `/internal/*` or `/docs*` publicly.**

## Conventions

- JSON over HTTP. Dates are ISO-8601 with an explicit offset (`2026-10-09T19:00:00+08:00` or `...Z`). Stored and returned in UTC.
- IDs are UUIDs issued by Planning (matching is case-insensitive; IDs are returned lower-case). Money is integer minor units: `3500` with `minorDigits: 2` is 35.00 of the round's `currency` (default `SGD`).
- Every response carries `x-request-id`. Send your own (8-64 chars of `A-Z a-z 0-9 _ -`) to correlate logs; otherwise one is generated.
- Bodies are limited to 100 kB (413 is returned as `INVALID_INPUT`). Unknown properties are rejected with 400.
- Round states: `COLLECTING` (accepts member writes) and `FROZEN` (no more writes).

### Authentication

| Route family | Credential |
| --- | --- |
| `/internal/*` | Header `x-internal-token: <shared secret>` (set `INTERNAL_API_TOKEN`, at least 16 chars, identically on callers). Missing: `401`; wrong: `403` |
| `/rounds/*` | The member's session: `Authorization: Bearer <session token>` or the session cookie (`SESSION_COOKIE_NAME`, default `what2do_session`); the bearer token wins if both are sent. Participation never trusts a member ID from the client; it asks Planning who the session belongs to. Production integration uses bearer tokens; cookie writes still need the gateway CSRF policy |
| Local development only | `AUTH_MODE=dev`: `Authorization: Bearer dev:<member-uuid>`. The plan is taken from the round. Refused when `NODE_ENV=production` |
 
`:roundId` in member routes must be a UUID (`400 INVALID_INPUT` otherwise).

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

`fieldErrors` appears only for `INVALID_INPUT` raised by validation.

| HTTP | `code` | Meaning | Retry? |
| --- | --- | --- | --- |
| 400 | `INVALID_INPUT` | Body, ID or state-of-answers failed validation (also oversized bodies, 413). See `fieldErrors` | Fix the request |
| 401 | `UNAUTHENTICATED` | Missing or unknown credential | Re-authenticate |
| 403 | `FORBIDDEN` | Valid credential but not allowed for this round, plan or roster | No |
| 404 | `NOT_FOUND` | Round not provisioned here, no snapshot yet, or no earlier response to copy | After provisioning/freezing |
| 409 | `STALE_VERSION` | `expectedRevision`, `acknowledgedOptionRevision`, a close-round confirmation review, or an RSVP selection is out of date | Reload, then resend |
| 409 | `ROUND_CLOSED` | Round is frozen; no more writes | No |
| 409 | `RESPONSES_INCOMPLETE` | Freeze refused: `requireComplete` or `countRespondedOnly` not satisfied | After more submissions, with a **new** `operationId` |
| 409 | `OPERATION_CONFLICT` | Provision/freeze ids, payload or roster reused or mismatched; copy over an existing draft; RSVP without a confirmed selection | No: fix the caller |
| 429 | `RATE_LIMITED` | Reserved; not issued today | Back off |
| 503 | `UPSTREAM_UNAVAILABLE` | Planning (authorisation or selection) or the database is unavailable. Fails closed | Yes, with backoff |
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
  ],
  "rosterPolicy": "publication",
  "memberIds": ["dddddddd-dddd-4ddd-8ddd-dddddddddddd"],
  "optionSnapshotId": "10101010-1010-4010-8010-101010101010",
  "currency": "SGD",
  "minorDigits": 2,
  "questions": [
    { "questionId": "12345678-1234-4234-8234-123456789abc", "required": true, "answerFormat": "text" }
  ]
}
```
 
| Field | Rule |
| --- | --- |
| `operationId` | Idempotency key. **Reuse the same value on retries** |
| `roundId`, `planId` | Planning's IDs |
| `optionRevision` | Integer >= 1: the published option revision members answer against |
| `activityIds` | 1-8 unique UUIDs: the only activities members may answer |
| `rosterPolicy` | Optional. `publication` (default): the published `memberIds` are the roster for the whole round. `close`: any authorised member of the plan may respond while collecting; the final roster is set at freeze. `close` requires `optionSnapshotId` |
| `memberIds` | Optional, 1-30 unique UUIDs. The published roster (enforced for `publication` rounds, and for any frozen round) |
| `optionSnapshotId` | Optional UUID: immutable identity of the published form. Copied into the snapshot. When set, `RATING` and `NO_PREFERENCE` activity answers are rejected (use question answers) |
| `currency`, `minorDigits` | Optional. `^[A-Z]{3}$` (default `SGD`) and integer 0-9 (default `2`), frozen for the round |
| `questions` | Optional, up to 100 (see below). When present, completeness is decided by the required questions |
 
`questions[]` entries: `questionId` (UUID), `required` (boolean), `answerFormat` (`text`, `choice`, `multi_choice`, `number`, `boolean`, `date_intervals`, `option_rating`, `date_poll`) and optional `choices` (up to 100; for `date_poll` the proposed dates as strings such as `"2027-06-01"`; for `choice`/`multi_choice` strings or `{ "choice_id": ... }` objects). IDs in `activityIds`, `memberIds` and `questions` must be unique ignoring case (`400` otherwise).
 
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
 
Idempotency: repeating the identical call (activity, member and question order do not matter) returns `200` with `alreadyProvisioned: true`. The same round or `operationId` with a *different* payload returns `409 OPERATION_CONFLICT`. A timeout is safe to retry. A new round (price/time/activity change) needs a new `roundId` and `optionRevision`.
 
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
  "answers": [
    { "question_id": "12345678-1234-4234-8234-123456789abc", "value": "Step-free access" }
  ],
  "updatedAt": "2026-10-06T00:20:00.000Z",
  "round": { "optionRevision": 1, "state": "COLLECTING" }
}
```
 
Availability is sorted by start time and activity answers by `activityId`. If the member has never saved: `revision: 0`, `status: "DRAFT"`, empty lists, `budget: { "kind": "UNANSWERED", "capMinor": null }`, `acknowledgedOptionRevision` set to the round's current revision, `updatedAt: null`.
 
Errors: `404` round not provisioned, `403` wrong plan or not on the roster.
 
## 3. Save my response (frontend)
 
`PUT /rounds/{roundId}/my-response`, member session. Replaces the whole draft. Partial drafts are allowed; completeness is checked at submission. Saving after a submit returns the response to `DRAFT`.
 
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
  "answers": [
    {
      "question_id": "12345678-1234-4234-8234-123456789abc",
      "value": "Step-free access is mandatory",
      "importance": "high"
    }
  ],
  "privateNote": "optional, never used by the algorithm, never shared"
}
```
 
Returns the saved response (same shape as section 2) with `revision` incremented.
 
| Field | Rules |
| --- | --- |
| `expectedRevision` | The `revision` you last loaded (`0` if never saved). Mismatch returns `409 STALE_VERSION`: reload and merge |
| `acknowledgedOptionRevision` | The `round.optionRevision` the form was rendered from. Must equal the current one, else `409 STALE_VERSION` |
| `availability[]` | Required (may be empty), up to 500 intervals the member **is** available. Each `endAt > startAt`, both on a 30-minute boundary, no overlaps, offset required. Unmarked time means unavailable |
| `budget` | Required object. `kind`: `UNANSWERED` (neither 0 nor unlimited), `CAP`, `UNLIMITED` (explicit "no limit") |
| `budget.capMinor` | Integer 0-100,000,000. **Required with `CAP`, forbidden otherwise.** `0` means free only |
| `activityAnswers[]` | Required (may be empty), at most 8, at most one per activity, only activities of this round. A missing activity means unanswered |
| `activityAnswers[].kind` | `RATING` (needs `rating` 0-4: 0 strongly dislike, 1 dislike, 2 neutral, 3 like, 4 love), `NO_PREFERENCE` (counts as neutral), `CANNOT_JOIN` (hard exclusion), `NEEDS_INFO` (candidate stays unresolved). `rating` is forbidden unless `kind` is `RATING`. Rounds with an `optionSnapshotId` reject `RATING` and `NO_PREFERENCE` |
| `answers[]` | Optional, up to 100 published-question answers (below) |
| `privateNote` | Optional, up to 1000 chars or `null` |
 
Order of checks: round and plan access (`404`/`403`), field and cross-field validation (`400`), then under the round lock: `409 ROUND_CLOSED` if frozen, `409 STALE_VERSION` for option or draft revision. Two saves racing from the same member: one wins, the other gets `409 STALE_VERSION`.
 
### Question answers
 
Each `answers[]` entry: `question_id` (UUID of a published question, at most once), `value` (required), optional `importance` (`low`, `normal`, `high`), optional `confirmed_requirement` / `confirmed_requirements` (opaque confirmation records kept in the snapshot), optional `reviewed_revision` (integer >= 1). Each answer's JSON must be at most 16,000 characters. Unknown or duplicate questions, and values that do not fit, are `400 INVALID_INPUT` with `answers.N` or `answers.N.value` field errors.
 
| `answerFormat` | Accepted `value` |
| --- | --- |
| `text` | string |
| `number` | finite number |
| `boolean` | `true` or `false` |
| `choice` | one of the published `choices` (string or number, or the `choice_id` of a choice object) |
| `multi_choice` | array of published `choices` |
| `date_intervals` | any array (contents are not checked here) |
| `date_poll` | object of at most 31 entries, each key a published date and each value `yes`, `maybe` or `no` |
| `option_rating` | object of at most 20 entries mapping an option id to a whole number 0-4 (0 not for me, 4 love it); option ids are not checked here |
 
Close-roster confirmations: in a `rosterPolicy: "close"` round, an answer carrying `confirmed_requirement(s)` is accepted only if the previously saved answer for that question has the same `value` and `reviewed_revision` equals the save's `expectedRevision`. Flow: save the answer, have Planning preview it (section 10), then save again with the confirmation and `reviewed_revision` set to the revision just saved. Otherwise `409 STALE_VERSION`.
 
## 4. Submit my response (frontend)
 
`POST /rounds/{roundId}/my-response/submit`, member session.
 
```json
{ "expectedRevision": 1 }
```
 
Requires a saved complete draft:
 
- question form (round has `questions`): every required question has a non-empty answer (an empty string, array or object does not count). Otherwise `400 INVALID_INPUT` on `answers`;
- legacy round: `budget.kind` is `CAP` or `UNLIMITED` and every activity of the round has an answer. Otherwise `400 INVALID_INPUT` with `budget` / `activityAnswers.N` errors.
Empty availability is allowed (unavailable everywhere). Returns the response with `status: "SUBMITTED"` and `revision` incremented. A retry with the pre-submit revision after a lost response returns the submitted response. Other errors: `409 STALE_VERSION` (wrong revision, no draft with a non-zero revision, or the draft's `acknowledgedOptionRevision` is behind the round), `409 ROUND_CLOSED`, and `400` if the member has no draft at all.
 
## 5. Copy earlier answers (frontend)
 
`POST /rounds/{roundId}/my-response/copy`, member session. Returns `200`.
 
```json
{ "sourceRoundId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" }
```
 
Creates the caller's draft (revision 1, `DRAFT`) in `roundId` from their response in `sourceRoundId`. Rules:
 
- both rounds must exist and belong to the caller's plan (`404`/`403`); `sourceRoundId` must differ from `roundId` and the target `optionRevision` must be higher, else `400 INVALID_INPUT` on `sourceRoundId`;
- `404 NOT_FOUND` if the caller has no response in the source round; `409 ROUND_CLOSED` if the target is frozen;
- copied: availability, private note, activity answers for activities still in the round, and `question_id` + `value` of answers for questions still published (importance and confirmations are not copied);
- budget is copied only when currency and `minorDigits` match, otherwise `UNANSWERED`;
- `acknowledgedOptionRevision` is set to the source's revision, so the member must review and save against the current revision before submitting;
- an existing draft is never overwritten: `409 OPERATION_CONFLICT`.
## 6. My RSVP (frontend)
 
`GET /rounds/{roundId}/my-rsvp`, member session.
 
```json
{
  "roundId": "0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33",
  "memberId": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  "revision": 0,
  "status": null,
  "summary": { "going": 3, "maybe": 1, "declined": 0, "total": 4 }
}
```
 
With a saved RSVP the stored record is returned (including `selectionVersion`, `status` and `revision`). `summary` counts every member's RSVP for the round.
 
`PUT /rounds/{roundId}/my-rsvp`, member session.
 
```json
{ "selectionVersion": 3, "expectedRevision": 0, "status": "GOING" }
```
 
| Field | Rules |
| --- | --- |
| `selectionVersion` | Integer >= 1: the selection version the member is answering |
| `expectedRevision` | Integer >= 0: the revision last loaded (`0` if none) |
| `status` | `GOING`, `MAYBE` or `DECLINED` |
 
Before writing, Participation reads Planning's current selection (see "Planning: current selection" below) and requires `plan_id` = the session's plan, `round_id` = the route, `selection_version` = the request and `is_current: true`; otherwise `409 STALE_VERSION`. Planning answering `404` or `409` gives `409 OPERATION_CONFLICT` ("confirm the current selection"); any other failure gives `503`. Then the write is revision-checked: a first RSVP needs `expectedRevision: 0`, updates need the stored revision and the same `selectionVersion`, and an exact retry of a completed write returns the stored RSVP. Mismatches are `409 STALE_VERSION`. An RSVP stays attached to the selection version it was created for. This call needs `PLANNING_BASE_URL` to be configured in every auth mode.
 
## 7. Freeze a round (Planning to Participation)
 
`POST /internal/rounds/freeze`, header `x-internal-token`.
 
Called when the organiser closes collection. Planning moves to review only after this returns 200. `memberIds` must be the same IDs Planning uses in session authorisation (`user_id` on plan members).
 
```json
{
  "operationId": "7c2e1a0b-3d45-4b68-8e2f-4d8b7a3f0b21",
  "roundId": "0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33",
  "memberIds": [
    "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
  ],
  "requireComplete": false,
  "countRespondedOnly": false,
  "optionSnapshotId": "20202020-2020-4020-8020-202020202020",
  "optionRevision": 1
}
```
 
| Field | Rule |
| --- | --- |
| `operationId` | Idempotency key. Reuse it on retries |
| `roundId` | The round to freeze |
| `memberIds` | 1-30 unique UUIDs, the final roster. For a round provisioned with a published roster under `publication`, it must equal that roster (`409 OPERATION_CONFLICT`). Members without a complete, current response are recorded as `incomplete` |
| `requireComplete` | Optional. Refuse unless every listed member is `complete` |
| `countRespondedOnly` | Optional. Early close: freeze with whoever has a complete, current submission; the others stay on the roster with `is_required_for_decision: false`. Refused if nobody qualifies |
| `optionSnapshotId` | Optional UUID of the final form identity. Required for `close` rounds. Replaces the round's stored value |
| `optionRevision` | Optional integer. If sent, must equal the round's `optionRevision` (`409 OPERATION_CONFLICT`). Required for `close` rounds |
 
Response `200`:
 
```json
{
  "roundId": "0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33",
  "snapshotId": "9a0b1c2d-3e4f-4a5b-8c9d-0e1f2a3b4c5d",
  "state": "FROZEN",
  "alreadyFrozen": false,
  "snapshot": { }
}
```
 
Behaviour:
 
- The freeze runs under an exclusive lock on the round. Saves in flight finish first and are included; later writes get `409 ROUND_CLOSED`.
- Idempotency: the same `operationId` and request (member order and UUID case do not matter) returns `alreadyFrozen: true` and the same `snapshotId`. A different roster, flags or `operationId` for an already frozen round is `409 OPERATION_CONFLICT`.
- `409 RESPONSES_INCOMPLETE` (from `requireComplete` or `countRespondedOnly`) leaves the round `COLLECTING` and **remembers the rejection**: retrying that `operationId` with the same payload is rejected again even if members have submitted since, and changing the payload under the same `operationId` is `OPERATION_CONFLICT`. Send a new `operationId` to try again.
- A snapshot larger than 1.5 MB is refused with `400 INVALID_INPUT` (field `responses`).
- Duplicate `memberIds` are `400`. Unknown round is `404`.
## 8. Response snapshot (Decision)
 
`GET /internal/rounds/{roundId}/response-snapshot`, header `x-internal-token`.
 
Returns the immutable snapshot stored at freeze (`schema_version: "response-snapshot-v2"`). Snake_case fields match `decision_service/algorithm-input-shape.md`. Private notes are omitted.
 
```json
{
  "schema_version": "response-snapshot-v2",
  "option_snapshot_id": null,
  "currency": "SGD",
  "minor_digits": 2,
  "snapshot_id": "9a0b1c2d-3e4f-4a5b-8c9d-0e1f2a3b4c5d",
  "round_id": "0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33",
  "plan_id": "c1a2b3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
  "option_revision": 1,
  "created_at": "2026-10-10T00:00:00.000Z",
  "participants": [
    { "participant_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "response_status": "complete", "is_required_for_decision": true }
  ],
  "constraints": [
    {
      "participant_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
      "availability": { "available_intervals": [{ "start_at": "2026-10-09T11:00:00.000Z", "end_at": "2026-10-09T13:00:00.000Z" }] },
      "budget": { "kind": "limited", "max_cost_minor": 3500, "currency": "SGD" },
      "required_attributes": [],
      "activity_flags": [{ "activity_id": "22222222-2222-4222-8222-222222222222", "flag": "needs_information" }],
      "candidate_flags": []
    }
  ],
  "preferences": [
    { "participant_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "activity_id": "11111111-1111-4111-8111-111111111111", "rating": 4 }
  ]
}
```
 
- Members are sorted by ID; every roster member appears, with empty constraints if they never answered.
- `response_status`: `complete` (answers complete and submitted at the current option revision), `stale` (acknowledged an older option revision), otherwise `incomplete`. `is_required_for_decision` is `true` for everyone unless the freeze used `countRespondedOnly`, then only for `complete` members.
- `participants[].answers` is present only for rounds with `questions`, and carries each member's `answers` as saved (values, `importance`, confirmation records).
- Budget mapping: `CAP` is `limited` (with `max_cost_minor`), `UNLIMITED` is `unlimited`, `UNANSWERED` or no response is `missing`; each carries `currency`.
- Preferences: `RATING` appears as given and `NO_PREFERENCE` as rating `2`. `CANNOT_JOIN` and `NEEDS_INFO` appear as `activity_flags` (`cannot_join`, `needs_information`); Decision must copy each activity flag onto every candidate of that activity as `candidate_flags` before running the algorithm. `required_attributes` and `candidate_flags` are always empty here.
Errors: `400` if `roundId` is not a UUID, `404` if the round is unknown or not yet frozen.
 
## 9. Progress (Planning)
 
`GET /internal/rounds/{roundId}/progress`, header `x-internal-token`.
 
```json
{
  "roundId": "0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33",
  "planId": "c1a2b3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
  "optionRevision": 1,
  "state": "COLLECTING",
  "submittedCount": 1,
  "draftCount": 1,
  "responses": [
    { "memberId": "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "status": "SUBMITTED", "decisionStatus": "complete" },
    { "memberId": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", "status": "DRAFT", "decisionStatus": "incomplete" }
  ]
}
```
 
Only members who have saved something are listed, sorted by ID; members with no response are not included. `decisionStatus` is `complete`, `incomplete` or `stale` as in the snapshot. No budgets, availability, notes or answers.
 
## 10. Preview a member's snapshot (Planning)
 
`GET /internal/rounds/{roundId}/members/{memberId}/preview-snapshot`, header `x-internal-token`.
 
Returns the same snapshot shape as section 8 for one member, built from their current saved response (nothing is stored), plus `response_revision` (0 if they have not saved). `snapshot_id` is a deterministic hash of round, member and revision, and `created_at` is the response's last update (or the Unix epoch if none). Planning uses it to interpret a member's answers, for example before the member confirms a requirement in a `close` round. `409 ROUND_CLOSED` once frozen, `404` for an unknown round, `400` if either ID is not a UUID.
 
## 11. Health
 
- `GET /health`: liveness, `{ "status": "ok" }`.
- `GET /health/ready`: readiness, checks the database. `503 UPSTREAM_UNAVAILABLE` if it is down. Use this for load balancer checks.
---
 
## What other teams must provide to Participation
 
### Planning: session authorisation (needed before production auth works)
 
Participation calls this on every member request and **fails closed** (503) if it cannot get an answer within 3 seconds. *Provisional: M1 and M3 to agree under F05.*
 
```
POST {PLANNING_BASE_URL}/internal/sessions/authorise
x-internal-token: <shared secret>
x-request-id: <request id>
 
{ "sessionToken": "<opaque token from the cookie/header>", "roundId": "<lower-case uuid>" }
```
 
`200`:
 
```json
{ "memberId": "<uuid>", "planId": "<uuid>", "roundId": "<same lower-case roundId>", "canRespond": true }
```
 
`401` unknown/revoked session, `403`/`404` not an approved member of that round's plan. Any other status is treated as unavailable (503). A `200` whose `roundId` differs from the request (compared exactly, so return it lower-case), whose IDs are not UUIDs or whose `canRespond` is not `true` is treated as `403`. Participation compares `planId` with the provisioned round and rejects a mismatch.
 
### Planning: current selection (needed for RSVP)
 
```
GET {PLANNING_BASE_URL}/internal/rounds/{roundId}/selection
x-internal-token: <shared secret>
```
 
`200`:
 
```json
{ "plan_id": "<uuid>", "round_id": "<uuid>", "selection_version": 3, "is_current": true }
```
 
`404` or `409` means there is no confirmed selection yet. The call has a 3 second timeout.
 
### Planning: lifecycle calls
 
- Publish: call provision (section 1) with a persisted `operationId`; mark COLLECTING only after `200`. Send Planning's `plan_rounds.id` as `roundId`, `plans.id` as `planId`, `proposed_activities.id` values as `activityIds`, the published roster as `memberIds`, and the current option revision as `optionRevision`. For question forms also send `questions`, `optionSnapshotId`, `currency` and `minorDigits`; use `rosterPolicy: "close"` (with `optionSnapshotId`) when the roster is only final at close.
- Monitor: `progress` (section 9) and `preview-snapshot` (section 10) while collecting.
- Close: call freeze (section 7) with the final roster `user_id`s (and `optionSnapshotId` plus `optionRevision` for `close` rounds); mark reviewing only after `200`. Retry the same `operationId` on timeouts; use a new one after `RESPONSES_INCOMPLETE`.
- RSVP: expose the selection endpoint above; members call section 6.
### Decision: data it reads
 
`GET /internal/rounds/{roundId}/response-snapshot` (section 8). Combine with Planning's option/candidate snapshot, expand `activity_flags` onto candidates, then call `run_decision_algorithm`.
 
## Quick local test
 
```bash
# 1. Open a round (as Planning)
curl -X POST http://localhost:3000/internal/rounds/provision \
  -H "content-type: application/json" -H "x-internal-token: local-dev-internal-token-change-me" \
  -d '{"operationId":"6b1d0f0e-2c34-4a57-9d1e-3c7a6f2e9a10","roundId":"0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33","planId":"c1a2b3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d","optionRevision":1,"activityIds":["11111111-1111-4111-8111-111111111111"]}'
 
# 2. Read my (empty) response as a dev member
curl http://localhost:3000/rounds/0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33/my-response \
  -H "authorization: Bearer dev:dddddddd-dddd-4ddd-8ddd-dddddddddddd"
 
# 3. Save, then submit
curl -X PUT http://localhost:3000/rounds/0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33/my-response \
  -H "content-type: application/json" -H "authorization: Bearer dev:dddddddd-dddd-4ddd-8ddd-dddddddddddd" \
  -d '{"expectedRevision":0,"acknowledgedOptionRevision":1,"availability":[],"budget":{"kind":"UNLIMITED"},"activityAnswers":[{"activityId":"11111111-1111-4111-8111-111111111111","kind":"NO_PREFERENCE"}]}'
curl -X POST http://localhost:3000/rounds/0f8a7c54-6d1f-4e0b-8a27-5b2d4f9c1e33/my-response/submit \
  -H "content-type: application/json" -H "authorization: Bearer dev:dddddddd-dddd-4ddd-8ddd-dddddddddddd" \
  -d '{"expectedRevision":1}'
```
 
(On Windows `cmd`, use the Swagger UI at `/docs` or Postman instead of these curl lines, since quoting JSON differs.)
