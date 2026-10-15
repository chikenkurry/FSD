# Decision HTTP load and worker recovery

Measured locally on 15 October 2026 using Docker Desktop on macOS ARM64,
Python 3.12 and PostgreSQL 16. These are single-run development measurements,
not production capacity guarantees or a statistically controlled comparison.

## Method

`benchmark_decision_service.py` starts a real API process and independent worker
processes sharing an isolated PostgreSQL schema. It submits 48 unique recommendation
jobs with 16 concurrent clients, fetches snapshots from local fixture HTTP services,
runs the real rules preprocessing/matcher, and polls the real result API.
Each worker process has one execution slot. Each case then sends 32 duplicate
requests and verifies they share one completed run ID.

One test variant adds 100 ms of blocking wait inside the harness before executing
each job, modelling an I/O-bound provider workload. This wait is not a model call,
and no artificial delay exists in production code. The second variant adds no wait.
Each case runs on the same local Docker host; there is no multi-node network test.

## Results

| Workload | Worker processes | Completed jobs/s | Admission p95 (s) | End-to-end p95 (s) | Errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rules + 100 ms simulated provider wait | 1 | 9.150 | 0.045 | 1.684 | 0 |
| Rules + 100 ms simulated provider wait | 2 | 17.495 | 0.042 | 0.958 | 0 |
| Rules, no simulated wait | 1 | 76.420 | 0.050 | 0.297 | 0 |
| Rules, no simulated wait | 2 | 59.761 | 0.039 | 0.278 | 0 |

The I/O-bound variant gained about 1.91 times the throughput with two worker
processes. The tiny rules-only workload lost throughput with a second process;
database, scheduling and request/polling overhead can dominate small jobs. This is
evidence for measuring before increasing replicas, not an assertion that extra
workers always improve performance. The small sample and local host introduce noise.

Each 32-request duplicate burst returned exactly one run ID. All unique jobs and
the shared duplicate job completed with the expected ranked domain result.
The [rules-only JSON output](evidence/decision_rules_local.json) retains the sampled
queue/worker metrics as well as the HTTP timings.

## Forced worker death

The harness starts a preview, waits for its database claim, and sends SIGKILL to
the owning worker process, bypassing graceful shutdown. A replacement worker uses
the same input/version and reclaims it after its five-second test lease expires.

| Check | Observed result |
| --- | --- |
| Same job/run ID after recovery | Yes |
| Attempts | 2 |
| Recovery after kill | Approximately 5.07 seconds |
| Late completion using the original token | Rejected |
| Domain result | Expected ready preview |

Production defaults to a 300-second lease with heartbeats; this five-second test
does not promise five-second production recovery. Graceful shutdown normally
surrenders unfinished claims sooner. Fencing protects the authoritative artifact;
provider requests can still repeat after a crash.

## Correctness coverage

Real PostgreSQL tests cover concurrent deduplication, distinct row claims,
SKIP LOCKED behaviour, crash fencing, global admission bounds, explicit retries,
shared first-value cache semantics, version/kind isolation, worker presence,
migration checksums, read-only schema verification, atomic legacy import, import
conflicts, uncheckpointed WAL preservation and controlled release retirement.
Separate HTTP tests cover admission without embedded execution, database/worker
readiness, preview pool isolation, restricted worker HTTP routes and fact-worker
identity matching without an API-held provider key. All 320 Decision tests passed
with PostgreSQL enabled, including 16 real PostgreSQL storage tests.
Existing connected lifecycle journeys run
against the Compose deployment with separate worker containers.

The local upgrade imported 70 stored artifacts and 46 job records from the stopped
SQLite deployment. The source was read-only; newly completed results live in
PostgreSQL. Every one of the 70 historical IDs, fingerprints and payloads was
verified unchanged against the source. Twelve connected lifecycle journeys passed
after the upgrade.

## Reproduce

Set `DECISION_TEST_DATABASE_URL` to a dedicated test-capable PostgreSQL database
and install `decision_service/requirements.txt`, then run from FSD:

```sh
python3.12 -m integration.benchmark_decision_service --jobs 48 --delay-ms 100 --output /private/tmp/decision-load.json
python3.12 -m integration.benchmark_decision_service --jobs 48 --delay-ms 0 --output /private/tmp/decision-rules-load.json
python3.12 -m unittest discover -s decision_service/tests -t . -q
python3.12 integration/test_http_lifecycle.py
```

The harness creates and drops generated `decision_bench_` schemas; database tests
use `decision_test_` schemas. No application tables are truncated. CI runs a smaller
24-job variant and uploads the generated JSON. No timing speedup threshold is
asserted in CI because shared-runner scheduling varies; failed jobs, duplicate
identities and incorrect crash/fencing results do fail the check.

This evidence does not measure live Gemini/Ollama performance, semantic accuracy,
large-roster/scenario complexity, API replica load balancing, extended saturation,
database failover or cloud autoscaling. Those require separate staging experiments.
See the [design document](../decision_service/docs/STORAGE_AND_WORKERS.md) for
deployment choices, alternatives and operating constraints.
