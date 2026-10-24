# Decision scoring, reads and idle-work optimisation

Measured locally on 15 October 2026 against baseline commit `c3b9163d`.
Scope: remove repeated scoring setup, unnecessary completed-result input reads,
history aggregation in readiness, and per-poll exhaustion cleanup.

## Design and unchanged behaviour

The generic matcher groups answers by participant/question/criterion and resolved
weights by participant once, when the first feasible candidate needs scoring.
Candidates then visit only that participant's own weighted answers. Question
identity stays in the key, so different questions about one attribute remain
distinct. Original answer/weight order, rounding, indifference, hard constraints,
missing-fact handling, tie-breaking and Pareto calculation are preserved.
An all-infeasible run does not prepare unused scoring lookups.

For C candidates, M members, P preferences and W total member-weight rows, the
previous lookup/weight traversal included O(C × (P + M × W)) work. It now includes
O(P + W) setup and O(C × W_required) weighted-row visits. Utility evaluation,
validation, constraints and the existing quadratic Pareto pass remain separate
costs; this is not an O(C × W) bound for the entire matcher.

Result retrieval uses one statement joining the requested ID to jobs and runs.
The statement sees one database snapshot. A CASE expression returns frozen inputs
only if the artifact is absent. This preserves completed/pending consistency
during concurrent completion and supports legacy artifacts without a job row.
Pending jobs still need their inputs to derive references and member/revision
metadata; this change does not claim those reads have disappeared. A separate
pending-metadata projection would require another migration and measured need.

Database readiness now calls `ping()` (`SELECT 1`); job-history counts remain in
diagnostic metrics. API readiness still checks compatible worker presence, and
worker readiness still checks its execution threads and heartbeat freshness.

Empty worker polls back off from 250 ms to 500 ms to one second. Processing work
or receiving a local admission notification resets that delay. Separate API
processes use the polling fallback; no cross-process event delivery is claimed.
The one-second cap bounds the polling component of idle admission delay under
normal database operation and matches the API's one-second Retry-After guidance.
Queue backlog, database waits and execution remain additional latency sources.

Expired leases with attempts remaining are reclaimed on the normal claim path.
Exhausted expired leases are failed at worker startup and on each process's
five-second maintenance cycle, rather than on every claim attempt. Live leases
are unaffected; stale tokens remain fenced. A partial lease index supports this
maintenance. Exhausted-job terminalisation may therefore wait until the next
maintenance cycle after expiry. Multiple workers can maintain safely using
SKIP LOCKED; this is per-process maintenance rather than a new global scheduler.

PostgreSQL LISTEN/NOTIFY was deferred: bounded adaptive polling meets the current
polling contract without another persistent listener connection per process and
its reconnect/fallback handling. Revisit notifications if measured idle job-start
latency requires a tighter target. No broker or cache infrastructure was added.

## Paired matching measurements

The baseline and optimised matcher ran in one macOS ARM64/Python 3.12 process,
alternating call order over 1,000 iterations per variant. Inputs were prepared
before timing. Timings include matcher validation/feasibility/scoring/Pareto,
and exclude preprocessing, database, HTTP and external model calls.

| Members / options | Baseline median (ms) | Optimised median (ms) | Change |
| --- | ---: | ---: | --- |
| 2 / 2 | 0.0294 | 0.0287 | Essentially unchanged at this scale |
| 10 / 4 | 0.1663 | 0.1456 | About 12% lower time |
| 30 / 8 | 0.9933 | 0.7069 | About 29% lower time |

All result fields except the generated run ID matched exactly. Separately sampled
Docker runs also produced identical result hashes for all three sizes. Those
independent timing samples showed noise on the tiny inputs; the raw evidence
retains them rather than claiming every sample improved.

## PostgreSQL measurements

Both variants used isolated PostgreSQL schemas in local Docker/Python 3.12.
Completed-read inputs contained 512 KiB of synthetic padding; the completed
artifact was the same fixture result. Readiness used 10,000 synthetic terminal
metadata rows. Timings are medians of 100 uninstrumented calls. Statement and
returned-field measurements were collected separately to avoid timing the counter.

| Operation | Baseline | Optimised |
| --- | ---: | ---: |
| Completed-result read statements | 2 | 1 |
| Completed-result materialised fields, JSON-encoded bytes | 542,918 | 15,985 |
| Completed-result read median | 0.8149 ms | 0.3029 ms |
| Readiness database-probe statements | 2 | 1 |
| Readiness database-probe median | 0.9190 ms | 0.1199 ms |
| SQL statements for one idle slot over four seconds, including startup/shutdown | 52 | 18 |

The completed-read field size decreased about 97%; the idle-window statement
count decreased about 65%. Encoded field sizes are an instrumentation proxy,
not measured PostgreSQL wire bytes. Readiness timings cover its database probe,
not the entire HTTP request and worker-presence checks. These are synthetic local
measurements, not production capacity or universal latency guarantees.

## Validation and reproduction

Regression checks cover repeated criteria in different questions, member-specific
weights, cheap readiness, bounded idle polling and local wake reset, exhausted
versus retryable/live leases, stale completion fencing, lightweight completed
reads, unknown IDs and historical artifacts. Existing ranking and lifecycle tests
continue to exercise the public behaviour. The full PostgreSQL-enabled suite
passed 327 tests.
All 12 connected HTTP journeys also passed. The 24-job HTTP/process smoke test
completed without domain errors, deduplicated each 32-request burst to one run,
and recovered a SIGKILLed preview with the same ID in about 5.01 seconds using its
five-second test lease; stale completion was rejected. This is a correctness
smoke check, not another controlled before/after throughput comparison.

[Raw baseline, optimised and paired evidence](evidence/decision_efficiency_local.json)
records the inputs/counts, timing summaries and equality checks. The independent
[HTTP/process load harness](benchmark_decision_service.py) additionally checks
duplicate admission and SIGKILL recovery; it does not impose noisy speed thresholds.

From FSD, set DECISION_TEST_DATABASE_URL to a test-capable PostgreSQL database:

```sh
git show c3b9163d:decision_service/generic_algorithm/run.py > /private/tmp/fsd-baseline-matcher.py
python3.12 -m integration.benchmark_decision_efficiency --reference-matcher /private/tmp/fsd-baseline-matcher.py --label optimised --output /private/tmp/decision-efficiency.json
python3.12 -m unittest discover -s decision_service/tests -t . -q
python3.12 integration/test_http_lifecycle.py
```

The harness creates/drops only generated `decision_eff_` schemas; it never
truncates application tables or makes model calls. Without a database URL it uses
temporary SQLite; that does not reproduce the PostgreSQL timings. Reference
matcher source is explicitly loaded from the supplied file for comparison.
