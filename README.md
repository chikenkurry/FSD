# What2Do

Planning, Participation and Decision provide this integrated backend flow:

```text
Create plan, options and questions
  → Publish a frozen form and facts
  → Invite members, collect answers and review private interpretations
  → Close collection and freeze the final roster and responses
  → Evaluate a durable recommendation job
  → Confirm a local selection snapshot and RSVP, or reopen a new round
```

This checkout provides backend APIs, durable recommendation jobs, private draft
previews, Gemini Search fact collection with evidence review, AI option research
(overviews, drafted questions and sourced option facts, with Google Places for venues), and
versioned RSVPs. The Vue frontend supports AI-assisted form creation, a step-by-step
member response flow, private review, recommendations, confirmation and RSVP. See [the full-system and frontend guide](frontend/README.md)
for startup, mobile testing, design choices and remaining UI scope. Legacy per-activity ratings return
`ACTIVITY_RATINGS_NOT_SUPPORTED`; the connected form uses question answers for
preferences. Activity participation flags and structured budgets are supported.

Decision uses PostgreSQL in the integrated stack, with separate API,
recommendation/fact workers and reserved preview workers. See the
[storage and worker design](decision_service/docs/STORAGE_AND_WORKERS.md) for the
architecture, alternatives, migration/rollback procedures and scaling limits, and
the [load/recovery report](integration/DECISION_LOAD_REPORT.md) for measured evidence.
Targeted scoring, database-read and idle-work improvements are measured in the
[Decision efficiency report](integration/DECISION_EFFICIENCY_REPORT.md).

## Run all services

Copy [.env_example](.env_example) to `.env` in this directory. Set `GEMINI_API_KEY` to
enable AI option research and fact collection, and optionally `GOOGLE_PLACES_API_KEY`
for venue photos, ratings and review summaries. Compose passes these keys only to the
Decision services that call those providers; see [option research](integration/OPTION_RESEARCH.md). See the
[backend lifecycle guide](integration/BACKEND_HARDENING.md) for job polling,
private previews, reviewed fact acceptance, RSVPs and service-specific local env files.

Requirements:

- Docker Desktop, or Docker Engine with Docker Compose v2, running.
- Internet access for the first build to download images and dependencies.
- Python 3 to run the cross-service checks; the HTTP test needs no extra packages.

Run these commands from the directory containing this README and
`compose.integration.yaml`. If your terminal opens in the parent workspace,
run `cd FSD` first.

When upgrading a running SQLite-based stack, stop the old writer first with
`docker compose -f compose.integration.yaml stop decision`. Startup imports its
retained volume read-only; do not delete it. Fresh installations need no old database.

```sh
docker compose -f compose.integration.yaml up -d --build --wait --wait-timeout 240
docker compose -f compose.integration.yaml ps
```

Open **http://localhost:15173** for the frontend. The stack starts the frontend,
three application services, separate Decision workers and
three PostgreSQL databases. It configures
their internal URLs and shared token, applies database migrations at startup,
and stores databases and Decision artifacts in named volumes. Local Go, Node
and PostgreSQL installations are not required for this setup.

See [core journey recovery](integration/CORE_JOURNEY_RECOVERY.md) for fact
correction/research, explicit approval, safe collection closure, new-round
revision, automatic result updates and server-backed draft recovery.

| Service | Responsibility | Local address |
| --- | --- | --- |
| Planning | Plans, options, questions, membership, guest sessions and round lifecycle | `http://127.0.0.1:18080` |
| Participation | Private drafts, submissions and frozen response snapshots | `http://127.0.0.1:13002` |
| Decision API | Snapshot validation, job admission and filtered results | Internal Docker network: `http://decision:8000` |
| Decision workers | Preprocessing, ranking and evidence collection; reserved preview and research pools | Internal health endpoints only |
| Participation PostgreSQL | Participation data; also available for database tests | `127.0.0.1:15432` |

Participation's Swagger UI is at [http://127.0.0.1:13002/docs](http://127.0.0.1:13002/docs).
Decision has no host port; call recommendations through Planning.

## Check the integration

Check the public services:

```sh
curl --fail http://127.0.0.1:18080/health
curl --fail http://127.0.0.1:13002/health/ready
```

Run the complete HTTP journeys:

```sh
python3 integration/test_http_lifecycle.py
```

These checks create randomly named users and plans in the integration databases.
They cover publication, submission, frozen snapshots, ranking, private member
review, confirmation and reopening. They also check that missing responses or
facts prevent an authoritative result, and that scheduled budgets and participation
flags reach the matcher. Test records remain in the local volumes.

The checks use explicit question definitions and synthetic facts. They cover late
joins, stale previews, concurrent recommendations, confirm/reopen races, sessions,
guest replacement and RSVP history. They do not measure live LLM interpretation accuracy.

## Use the APIs

Create a guest session through Planning:

```sh
curl --fail -X POST http://127.0.0.1:18080/v1/users \
  -H 'Content-Type: application/json' \
  -d '{"username":"Your name"}'
```

Keep the returned `session_token` and send `Authorization: Bearer <session_token>`
to both public services. Planning checks membership; members join plans through
invitations. A username or user ID alone does not authenticate a request.

The [integration guide](integration/README.md) documents option facts, question
definitions, request bodies and the lifecycle endpoints. It also explains the
supported execution modes and the limits of each adapter.

The Compose credentials and shared internal token are local development defaults.
Set `INTERNAL_API_TOKEN` to a deployment-specific value of at least 16 characters
when running elsewhere, and keep `/internal/*` routes behind the internal network.

## Local LLM interpretation

CI sets `SEMANTIC_PROVIDER=rules`, because GitHub runners have no Ollama server.
The default `SEMANTIC_PROVIDER=ollama` enables model-assisted interpretation of
member answers. Run Ollama separately with the configured model installed and
reachable from Docker, then start the stack. Compose connects to Ollama on the
host; it does not launch an Ollama container:

```sh
SEMANTIC_PROVIDER=ollama \
OLLAMA_BASE_URL=http://host.docker.internal:11434 \
OLLAMA_MODEL=qwen3:4b-instruct \
docker compose -f compose.integration.yaml up -d --build --wait
```

Set `SEMANTIC_PROVIDER=rules` explicitly for model-free operation. Offline
evaluation and benchmark tools retain their deterministic rules baseline.

Change the URL and model to match your Ollama installation. Model outputs still
pass preprocessing validation before ranking. This enables interpretation of
answers. Gemini handles organiser-side research separately when GEMINI_API_KEY is
configured: option overviews, drafted questions and sourced option facts
([option research](integration/OPTION_RESEARCH.md)), plus quoted fact collection.

## Logs and shutdown

```sh
docker compose -f compose.integration.yaml logs -f planning participation decision
docker compose -f compose.integration.yaml down
```

`down` stops the stack and retains its data volumes. Run the startup command again
to resume. If a Prisma engine download fails because the builder cannot trust
your network's certificate authority, follow the verified engine-cache steps in
the [integration guide](integration/README.md#run-and-check).

## Service documentation

- [Integration guide and API lifecycle](integration/README.md)
- [Facts, semantics and deterministic ranking](decision_service/docs/FACTS_AND_SEMANTICS.md)
- [AI option research, Google Places and sourced option facts](integration/OPTION_RESEARCH.md)
- [Shared snapshot schemas](contracts/snapshots.schema.json)
- [Decision setup and examples](decision_service/docs/README.md)
- [Decision processing flow](decision_service/docs/FLOW.md)
- [Decision algorithm input contract](decision_service/docs/algorithm-input-shape.md)
- [Participation setup](participation-service-main/README.md)
- [Participation API reference](participation-service-main/docs/API.md)

Current preprocessing adapters use `decision_service/algorithm` and
`decision_service/generic_algorithm`. The earlier standalone algorithm remains in
`decision_service/app/algorithm`.
