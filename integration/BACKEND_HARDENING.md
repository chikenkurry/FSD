# Backend lifecycle and execution

Decision's PostgreSQL/process-splitting milestone is described in
[Storage and worker design](../decision_service/docs/STORAGE_AND_WORKERS.md),
including alternatives, first migration, rollback and measured scaling evidence.

New rounds use: draft → publish form → collect and review → freeze final roster/responses
→ evaluate a durable run → confirm a local selection snapshot → RSVP.
Planning owns identity and lifecycle; Participation owns private answers and attendance;
Decision owns interpretation, supported adapters, execution and evidence.

## Environment files

For the integrated stack, copy `FSD/.env_example` to `FSD/.env`. Compose reads
this root file and explicitly projects variables into each container. Only Decision's recommendation/fact worker
receives `GEMINI_API_KEY`. Planning and Participation receive their own database
URLs and internal connection settings. Do not use `env_file: .env` for every service.

For separate local processes, each service has its own `.env_example`.
Planning loads its working directory's `.env`; Participation's start scripts use
Node's env-file support. Start Decision from FSD with:

```sh
python3.12 -m decision_service.service --env-file decision_service/.env
```

All three must use the same internal token. Service templates use local process
ports 8080/3000/8000 and each service's standalone development database. The root
Compose stack uses the Docker network internally and ports 18080/13002 externally.
Real env files, editor copies, local SQLite files and dependency caches are ignored.

## Publication, membership and freezing

The published form remains immutable. Its roster records members present at
publication and is marked `roster_is_final: false`. Membership can change during
COLLECTING for new close-roster rounds. Invitation admission, definition edits and
lifecycle transitions serialize on Planning's plan row. Joining after closing is a
409. A published question, fact, option or decision-goal change requires a new draft.

Closing records a separate immutable evaluation definition, final roster and
snapshot ID in Planning before asking Participation to freeze. Participation
validates the form revision and freezes that exact roster/identity under its existing
round write guard. A join committed before the Planning cutoff is included; a later
join is rejected. An in-flight answer committed before Participation's freeze is included.

Historical rounds keep their publication-roster policy. Their snapshot IDs and
selection/run references are retained. `PlanRound` describes draft metadata;
`PublishedRound` owns lifecycle state, with one row per published draft. Plan state
and draft active flags are projections changed by lifecycle commands.

Planning retries persisted PUBLISHING/LOCKING handoffs every 15 seconds, including
after restart. No database lock spans a network call. Command IDs and payloads are
reused. Form and response snapshots are limited to 1.5 MB each.

## Private review before closing

`GET /v1/rounds/{id}/readiness` reports collection progress and definition issues.
Known unsupported scheduled definitions are rejected at publication. Connected
forms reject legacy ratings at save; question answers carry preferences.

A member starts a private preview:

```json
{"expected_revision": 2}
```

Send it to `POST /v1/rounds/{id}/preview`, then poll
`GET /v1/rounds/{id}/preview`. The result contains only that member's interpretations,
issues, response revision and run ID. It checks adapter compatibility without ranking.
Editing the response invalidates the preview; an old revision returns 409.

For a new round, save an answer before confirming its interpretation. A confirmation
answer carries `reviewed_revision` equal to the draft's `expectedRevision`, plus
`confirmed_requirement` or `confirmed_requirements`. The value must still match
the saved answer. Preprocessing checks the interpreted meaning against the confirmation.
To change that value, save it without the old confirmation and review the new revision.
Copying answers into a new round clears old confirmations and still requires resubmission.

## Durable recommendation jobs

`POST /v1/rounds/{id}/recommendations` returns 202 while queued/running, with
`Retry-After: 1`, a stable `run_id`, `status: pending` and `job_state`.
Poll `GET /v1/rounds/{id}/recommendation`; terminal domain results return 200.
A terminal processing failure is `status: failed` with a safe issue code.

The job key covers frozen input content, processing version, implementation hash,
model identity/revision and execution policy. Duplicates are found before computation.
Accepted model replies are cached privately by exact method/input/version, including
across previews and recommendations. Completed artifacts retain their semantic evidence.

Jobs share a durable store; each worker pool claims available compatible kinds
in creation order, with a separate preview pool in Compose.
Transactional claims, lease heartbeats and fenced completion prevent two workers from
publishing competing artifacts. Expired work is recovered after restart. There are
at most 128 pending jobs and three automatic attempts. Each worker process has
1–8 slots; the integrated stack reserves a separate preview worker pool.
The default job budget is 180 seconds; individual provider requests respect the
remaining budget. The initial SQLite import explicitly fails pending work from
the previous implementation instead of recomputing it under the wrong version.
Later rolling releases retain version-specific queues; old workers drain their
own jobs, or an operator explicitly retires their implementation after shutdown.

Resend the original POST with `"retry": true` to retry an exhausted job after
resolving its cause. Successful results remain immutable. A new implementation or
model revision creates a new input key. Change `SEMANTIC_MODEL_REVISION` when
replacing local model weights under the same name.

The integrated deployment uses PostgreSQL for the shared queue, results and
semantic cache. SQLite remains a single-deployment fallback for standalone local
work. See the storage design for cache limitations and multi-replica operations.

## Confirmation and RSVP

Planning verifies the active run and eligible candidate, then checks the latest round
again inside its local transaction. It persists candidate facts, scheduling/scenario
details, currency convention, timezone and both input references with a selection
version. Reading confirmation does not need Decision online.

The legacy `GET /v1/confirmed-selection/plans/{plan_id}` delegates to the authoritative
selection; the old unrestricted write remains blocked. Earlier integrated selections
are backfilled with their original immutable definition and candidate reference.
The retired legacy selection table remains readable for historical records.

Participation exposes `GET/PUT /rounds/{round_id}/my-rsvp`:

```json
{"selectionVersion": 1, "expectedRevision": 0, "status": "GOING"}
```

Statuses are GOING, MAYBE and DECLINED. The caller is derived from their session.
Revision checks protect edits and identical retries. Answers attach to the exact
selection. Reopening blocks further RSVP writes to the old selection and preserves
its history; predicted availability never creates an RSVP.

## Gemini fact collection

Configure `GEMINI_API_KEY` and optionally `GEMINI_FACT_MODEL` in the root env file.
Member interpretation remains rules/Ollama; Gemini is a separate evidence collector.
The collector follows Google's [Search grounding documentation](https://ai.google.dev/gemini-api/docs/generate-content/google-search)
and [GenerateContent API](https://ai.google.dev/api/generate-content).

Give an option `metadata.identity` containing an exact `model_id` or `source_url`,
and optional variant/region. Collect facts before publication when possible:

```json
{
  "requests": [
    {"option_id":"<option UUID>","attribute_id":"mass","value_type":"number","unit":"g"}
  ]
}
```

Send this to `POST /v1/rounds/{draft_or_published_id}/fact-collection` and poll
the matching GET endpoint. Only option identities, requested criteria, currency and
cost scope leave Decision. Rosters, questions, free-form plan context and member
responses are excluded. The collector first searches, then extracts typed claims
from the grounded text. It validates exact identities, units, value-bearing evidence,
citation support and expiry, and preserves conflicts and qualifiers.

Claims remain pending/estimated. Citation metadata does not independently establish
source truth. The result retains Google search suggestions and grounding metadata;
future UI must render suggestions according to the provider requirements and handle
returned HTML as untrusted content.

An organiser reviews the source and applicability, then sends to a current,
unpublished draft round:

```json
{
  "operation_id":"<UUID>",
  "collection_run_id":"<returned run UUID>",
  "claim_ids":["<claim hash>"],
  "reviewed":true,
  "replace_existing":false
}
```

Endpoint: `POST /v1/rounds/{draft_id}/accept-facts`. Published rounds require reopening.
Acceptance is transactional and idempotent, belongs to the same plan, preserves
provenance, rejects expired/qualified claims, and requires an explicit replacement
flag for conflicting confirmed values. Select one claim per option/criterion.
Qualified claims such as “up to” remain available for investigation, not silently
promoted to an exact measurement.

The normal test suite mocks Gemini. The optional --accept-reviewed smoke mode
verifies a known public specification before exercising explicit acceptance and ranking. Run the explicit live smoke test only when
intending to make provider calls:

```sh
python3.12 integration/test_fact_collection_live.py
```

## Sessions, operations and verification

`POST /v1/session/rotate` replaces the presented credential; `/revoke` invalidates it.
Guest recovery is organiser-assisted: register a replacement guest, then
`POST /v1/plans/{plan_id}/replace-member` with `previous_user_id` and
`replacement_user_id`. It is plan-scoped, never uses display-name matching and
does not copy old private answers. Organiser recovery still requires an external
identity provider; it cannot safely be inferred from a lost guest credential.

Planning uses checked-in SQL migrations with checksums and an advisory transaction
lock. Complete existing schemas are adopted as the baseline; partial schemas fail
validation. Participation uses Prisma migrations. Decision uses checked-in,
checksummed PostgreSQL migrations and an atomic read-only SQLite import preserving
historical IDs/artifacts; runtime processes verify the migrated schema.

All services have database readiness checks, request IDs and safe error envelopes.
Planning propagates request IDs to its peers; Participation propagates them during
authorisation. Decision emits job/model timing logs and internal queue counts.
Planning admission limits are local to a process; deployment gateways must keep
internal routes private and apply shared limits across replicas.

```sh
python3.12 -m unittest discover -s decision_service/tests -t . -q
python3.12 -m integration.benchmark_backend
python3.12 integration/test_http_lifecycle.py
```

CI checks all services, Participation database tests and the full Compose journey.
Benchmarks separate snapshot mapping, rules preprocessing and matching. They are
synthetic timing measurements, not live-model latency or accuracy evidence.
Independent human labelling/review of held-out semantic examples remains required;
the collector and regression suite do not establish arbitrary-input accuracy.

## Verification before the PostgreSQL milestone

Decision: 299 tests; Participation: 64 unit tests and 17 database tests;
connected lifecycle: 12 HTTP journeys; Planning tests run during image builds.
The live Gemini smoke check exercised collection, explicit reviewed acceptance,
idempotent replay, published-definition protection and authoritative ranking.
The structured evaluation passed 22/22 authored cases (116/116 assertions).
Rules-only median preprocessing plus matching was about 3.7 ms at 30 members/8
options on this local machine; this excludes model calls and network latency.
