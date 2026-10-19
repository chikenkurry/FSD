# Service integration

The integrated Vue frontend is at **http://localhost:15173** after Compose starts.
See [full-system startup and mobile/browser testing](../frontend/README.md).

Decision now uses shared PostgreSQL persistence and separate API/worker roles.
See [the design and alternatives](../decision_service/docs/STORAGE_AND_WORKERS.md)
for first-upgrade instructions, version compatibility, operations and scaling,
and [the load/recovery report](DECISION_LOAD_REPORT.md) for measured evidence.

See [backend hardening](BACKEND_HARDENING.md) for the new close-roster policy,
202 job polling, private previews, Gemini collection/review, migrations and RSVPs.
Older rounds retain their publication-roster policy and immutable history.

Planning owns form definitions, option facts, membership and round transitions.
Participation owns private answers and freezes them. Decision reads both frozen
snapshots, preprocesses answers, adapts supported inputs and stores recommendation
artifacts. Gemini Search can collect candidate claims for organiser review.

## Code structure

| Service | Code | Responsibility |
| --- | --- | --- |
| Planning | `app/internal/integration/handler.go`, `selection.go` | Decode HTTP requests, call upstream services and translate results. |
| Planning | `round_store.go`, `selection_store.go` | Store round transitions and selections, with transaction locks and retry checks. |
| Planning | `auth.go`, `sessions.go`, `access_policy.go` | Authenticate sessions, resolve membership and guard mutations. |
| Decision | `service/__main__.py`, `http_api.py` | Configure the service and handle internal HTTP requests. |
| Decision | `service/workflow.py`, `execution.py` | Preprocess frozen inputs, prepare executor handoffs and run the selected matcher. |
| Decision | `service/views.py`, `store.py` | Filter public/member output and persist private artifacts. |
| Decision | `generic_option_contract.py` | Check structure, references, facts, rules and weights before matching. |
| Participation | `src/responses/response-rules.ts`, `question-answer-rules.ts`, `response-completeness.ts` | Validate drafts and use the same completeness rules for submission and snapshots. |
| Participation | `src/responses/decision-snapshot.ts`, `src/prisma/` | Serialize frozen responses and implement persistence. |

Planning makes upstream calls outside database transactions. Round changes keep
their locks and stale-reference checks inside the store methods. Participation's
response service depends on completeness rules rather than snapshot serialization.
Decision's views enforce member privacy independently of matcher execution.

## Run and check

For prerequisites, service URLs, optional Ollama configuration and shutdown
commands, see [the project quick start](../README.md#run-all-services).
From the directory containing `compose.integration.yaml`:

```sh
docker compose -f compose.integration.yaml up -d --build --wait
python3 integration/test_http_lifecycle.py
```

Planning runs at `http://127.0.0.1:18080`, Participation at
`http://127.0.0.1:13002`. Decision is reachable only inside the Docker network.
The stack uses separate database volumes. The HTTP tests create random test users
and plans and retain their frozen history in these isolated volumes.

Participation's test database is on localhost port 15432:

```sh
cd participation-service-main
DATABASE_URL=postgresql://participation:participation@127.0.0.1:15432/participation npm run test:e2e
```

The default semantic mode is `rules`. For arbitrary prose, configure
`SEMANTIC_PROVIDER=ollama`, `OLLAMA_BASE_URL` and `OLLAMA_MODEL` before starting
the stack. Missing interpretations return review requests. The HTTP tests use
explicit definitions and synthetic facts; they do not measure live model accuracy.

Python's unittest suite needs both package roots for the legacy algorithm tests:

```sh
python3 -m pip install -r decision_service/requirements-test.txt
PYTHONPATH=.:decision_service python3 -m unittest discover -s decision_service/tests
```

The function-based activity adapter and legacy algorithm tests also run under
pytest with the same `PYTHONPATH`. Planning's checks use `go test ./...` from
`planning-service`; Participation provides `npm run typecheck` and `npm test`.

Prisma normally downloads engines during the build. If the builder cannot trust
the network's CA, configure that trust or cache the exact engines over verified
HTTPS on the host. After installing Participation's dependencies, for ARM64 Linux:

```sh
python3 integration/cache_prisma_engines.py --target linux-arm64-openssl-3.0.x
```

AMD64 Debian uses `debian-openssl-3.0.x`. The helper reads the installed Prisma
engine version and checks the published archive hashes. The build checks the
cached version, platform and content hashes. Cached binaries are ignored by Git.
TLS verification remains enabled.

## Sessions

`POST /v1/users` accepts `{"username":"Name"}` and returns an opaque
`session_token` once. This implements guest identity, rather than password
accounts. Store the token privately and send `Authorization: Bearer <token>` to
both public services. Planning stores its hash with a 30-day expiry and checks
plan membership. Display names and user IDs alone grant no access.

Organisers create and edit their plans. Members join through invitations.
Participation asks Planning's internal session endpoint to resolve the user
against the published roster. Internal routes require `x-internal-token` and
must remain off a public gateway. Supply a deployment-specific
`INTERNAL_API_TOKEN`; the Compose default is for local tests.

## Form definitions

Existing CRUD endpoints create plans, options and questions. Sourced option facts
go in `metadata.facts`:

```json
{"facts":[{
  "criterion":"max_cost", "value":"20.00", "value_type":"decimal",
  "unit":"SGD", "status":"confirmed", "source":"reviewed supplier quote",
  "context":{"scope":"per_person_total"}
}]}
```

The old `est_cost_per_person` display column is not promoted to a confirmed fact.
Its default zero does not establish a free option. Unknown facts use null and a
declared type. Confirmation records the organiser's accepted claim; this service
does not independently verify the external source.

Question UUIDs become `question_id`. Custom choices live in `options.options` as
strings or `{choice_id, label}` objects. Optional leader bindings go in
`options.decision`:

```json
{"decision":{
  "role":"soft", "criterion":"mass", "relevance":1,
  "answer_format":"number", "numeric_intent":"target",
  "mapping":{"value_type":"number","unit":"kg",
             "comparison_rule":"numeric_target_v1","scale":0.4}
}}
```

Ordinary labels can use the semantic provider when bindings are omitted. Formats
are text, choice, multi-choice, number, boolean and date intervals. Use text for
monetary quantities needing an exact decimal string. Targets need a source-derived
or leader-declared scale.

## Lifecycle API

| Request | Purpose |
| --- | --- |
| `POST /v1/rounds/plans/{plan_id}` | Create a draft round. |
| `POST /v1/rounds/{id}/publish` | Freeze the form and facts; validate; provision Participation and open membership collection. |
| `GET /v1/rounds/{id}/form` | Read the published definition. |
| `PUT /rounds/{id}/my-response` on Participation | Replace the caller's draft with revision checking. |
| `POST /rounds/{id}/my-response/submit` on Participation | Submit and advance the response revision. |
| `POST /v1/rounds/{id}/close` | Close writes and save the frozen response snapshot reference. |
| `POST /v1/rounds/{id}/recommendations` | Preprocess and match the frozen inputs. |
| `GET /v1/rounds/{id}/recommendation` | Read the aggregate result and missing fact requests. |
| `GET /v1/rounds/{id}/clarifications` | Read only the caller's interpreted constraints and preferences. |
| `POST /v1/rounds/{id}/confirm` | Confirm an eligible candidate from the current run. |
| `POST /v1/rounds/{id}/reopen` | Create a new round for corrections. |
| `POST /rounds/{new_id}/my-response/copy` on Participation | Copy earlier answers into a draft requiring review. |

Publish settings include `currency`, `currency_minor_digits`, `cost_scope`,
`timezone` and `execution_mode`. Modes are `options`, `scheduled` and `scenarios`.
Optional criterion declarations, aliases, scenario costs and group objective are
frozen with the definition. Retries reuse stored operation IDs and the original
definition; changing publish settings requires a new round.

Option and question edits after publication require a new draft round. New rounds
allow roster changes during collection and freeze the final roster at closing.
Reopening accepts `{"operation_id":"<uuid>"}`. Confirmation accepts
`{"operation_id":"<uuid>","run_id":"<uuid>","candidate_id":"<returned ID>"}`.
It checks the current round, input references, run and eligibility before committing
a selection. The earlier unrestricted selection-create endpoint is blocked.
Ordinary CRUD cannot delete confirmed history.

A generic draft has this shape:

```json
{
  "expectedRevision":0, "acknowledgedOptionRevision":1,
  "availability":[], "budget":{"kind":"UNANSWERED"}, "activityAnswers":[],
  "answers":[{"question_id":"<published question UUID>","value":1.2}]
}
```

Requirement confirmations use `confirmed_requirement` or `confirmed_requirements`
on the corresponding answer, with `attribute_id`, `required_value`,
`constraint_rule` and `unit`. Preprocessing verifies that the review matches its
interpretation. Saving after submission returns to draft. An old revision cannot
undo submission; retrying the same submit remains valid.

For new rounds, confirmations also carry `reviewed_revision` equal to the draft
revision being saved, and the reviewed value must match the previously saved answer.
Use the private preview before confirming; see [the review flow](BACKEND_HARDENING.md#private-review-before-closing).

Copying accepts `{"sourceRoundId":"<earlier round UUID>"}` and never overwrites
an existing draft. Copied answers retain the old acknowledged option revision.
Members must review, save with the new revision and resubmit. Removed question and
activity IDs are not copied; changed currency/precision clears the structured budget.

## Execution and limits

Ordinary decisions use `generic-option-v1` and executor
`generic-option-baseline-v2`, supporting numeric, boolean, categorical and tag-set
criteria. Incomplete responses, contradictions, unresolved comparisons and missing
evidence block authoritative ranking. Unknown candidates are not silently discarded
to rank a subset.

Scheduled decisions use the existing `activity-v2` subset. Put concrete candidates
in option `metadata.candidates`, with `candidate_id`, `start_at` and `end_at`, and
collect timestamp availability in Participation. The bridge converts exact major
amounts into declared minor units and expands activity flags onto candidates.
Compatible budget ceilings use the tightest limit. Personal weight changes,
numeric utilities and date-only availability that the activity scorer cannot
represent return `unsupported`; they are not omitted. Whole-day scenarios use
the scenario adapter and require matching confirmed cost evidence.

Shared wire shapes are in [the schema](../contracts/snapshots.schema.json).
Runtime validation also enforces snapshot identity, roster, currency, question
references and member weights. Full semantic evidence and member processing stay
in Decision's private PostgreSQL store (SQLite is a standalone fallback). Shared results contain aggregate scores and
issues without raw answers, budgets or private notes.

The connected form uses question answers for preferences. Legacy per-activity
ratings have a different scoring contract and return `ACTIVITY_RATINGS_NOT_SUPPORTED`
if supplied; they are not silently discarded. Activity participation flags and
structured budgets are supported.

The frontend connects ordinary option forms, private review, recommendation,
confirmation and RSVP. Dedicated Gemini collection and scheduled/scenario creation
screens remain separate UI work. Gemini collection, RSVP and durable jobs are documented in the backend guide.
External identity providers remain separate work. Planning uses checked-in, versioned SQL migrations. Participation's new rating constraint refuses existing invalid
null-rating rows rather than guessing their meaning.
