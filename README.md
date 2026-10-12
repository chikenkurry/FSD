# What2Do

Planning, Participation and Decision are integrated on `feat/service-integration`
for the supported backend flow:

```text
Create plan, options and questions
  → Publish a frozen form, facts and roster
  → Members save and submit private answers
  → Close collection and freeze responses
  → Preprocess answers and rank supported candidates
  → Review and confirm a result, or reopen a new round
```

This checkout provides backend APIs. Frontend form and review screens, automated
web fact collection and RSVPs remain to be implemented. Organisers currently
supply reviewed option facts. Legacy per-activity ratings return
`ACTIVITY_RATINGS_NOT_SUPPORTED`; the connected form uses question answers for
preferences. Activity participation flags and structured budgets are supported.

## Run all services

Requirements:

- Docker Desktop, or Docker Engine with Docker Compose v2, running.
- Internet access for the first build to download images and dependencies.
- Python 3 to run the cross-service checks; the HTTP test needs no extra packages.

Run these commands from the directory containing this README and
`compose.integration.yaml`. If your terminal opens in the parent workspace,
run `cd FSD` first.

```sh
docker compose -f compose.integration.yaml up -d --build --wait
docker compose -f compose.integration.yaml ps
```

The stack starts all three services and two PostgreSQL databases. It configures
their internal URLs and shared token, applies database migrations at startup,
and stores databases and Decision artifacts in named volumes. Local Go, Node
and PostgreSQL installations are not required for this setup.

| Service | Responsibility | Local address |
| --- | --- | --- |
| Planning | Plans, options, questions, membership, guest sessions and round lifecycle | `http://127.0.0.1:18080` |
| Participation | Private drafts, submissions and frozen response snapshots | `http://127.0.0.1:13002` |
| Decision | Preprocessing, execution adapters, ranking and stored results | Internal Docker network: `http://decision:8000` |
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

The checks use explicit question definitions and synthetic facts. They do not
measure live LLM interpretation accuracy.

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

## Enable local LLM interpretation

The default `SEMANTIC_PROVIDER=rules` runs without an LLM. It supports explicit
definitions and rule-based interpretation; unresolved answers request review.

For model-assisted natural-language interpretation, run an Ollama server with
the configured model installed and reachable from Docker, then start the stack:

```sh
SEMANTIC_PROVIDER=ollama \
OLLAMA_BASE_URL=http://host.docker.internal:11434 \
OLLAMA_MODEL=qwen3:4b-instruct \
docker compose -f compose.integration.yaml up -d --build --wait
```

Change the URL and model to match your Ollama installation. Model outputs still
pass preprocessing validation before ranking. This enables interpretation of
answers; web fact collection remains separate work.

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
- [Shared snapshot schemas](contracts/snapshots.schema.json)
- [Decision setup and examples](decision_service/docs/README.md)
- [Decision processing flow](decision_service/docs/FLOW.md)
- [Decision algorithm input contract](decision_service/docs/algorithm-input-shape.md)
- [Participation setup](participation-service-main/README.md)
- [Participation API reference](participation-service-main/docs/API.md)

Current preprocessing adapters use `decision_service/algorithm` and
`decision_service/generic_algorithm`. The earlier standalone algorithm remains in
`decision_service/app/algorithm`.
