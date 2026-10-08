# Preprocessing evaluation

The evaluation runner compares preprocessing output with authored labels across
purchase, trip, event, project, and museum-exhibit decisions. It uses the public
`preprocess` function. Expected labels are never passed to preprocessing or the
semantic provider.

The [dataset](../fixtures/evaluation/cases.json) contains 34 synthetic development
examples: 22 structured cases and 12 semantic cases. It covers choices, numeric
targets, budget shorthand, dates, indifference, missing answers, units, unknown
facts, conflicting limits, leader weights, paraphrases, negation, inferred hard
requirements, question relevance in different decisions, compound answers,
numeric directions/ranges/strict bounds, and member importance including cycles.
Facts are fictional. Dataset version 3 added ten examples for richer meanings;
version 4 adds six for criterion/tag aliases, model synonyms, and distinct related
concepts. Version 5 declares formerly implicit numeric targets and replaces the
different-budget rejection label with compatible upper limits. Snapshot IDs
change where numeric intent declarations change. These remain authored
development cases, not independent held-out data.
The team should review the labels before using the results as capstone evidence.
These examples are not a held-out benchmark and cannot establish accuracy on
arbitrary user input.

## Run

Run commands from `FSD`. The runner uses the Python standard library and the
existing semantic providers; no additional dependencies are required.

### Rules baseline

```sh
python3 -m decision_service.evaluation --output /tmp/preprocessing-rules.json
```

The current rules run passes **23/34 cases and 148/185 assertions**, with no
operational errors. The eleven failed cases cover runtime paraphrasing, mixed
positive/negative preferences, an inferred accessibility requirement, an
irrelevant subject question, a hard task exclusion, compound text, compound
numeric directions, an importance paraphrase, and the three model canonicalization
checks. These are recorded
failures, not skipped cases. This command returns exit code `1`.

For the structured regression subset:

```sh
python3 -m decision_service.evaluation --tag structured
```

That subset passes **22/22 cases and 116/116 assertions**. Tags describe the input,
not a restriction on provider use. Repeat `--tag` to require all specified tags:

```sh
python3 -m decision_service.evaluation --tag semantic --tag negation
```

Use `--tag canonicalization` for the six alias/equivalence development cases.

## Separate processing challenge set

[processing_challenge.json](../fixtures/evaluation/processing_challenge.json)
contains 24 new synthetic examples across warehouse, printer, venue, and server
decisions: 20 structured cases and four natural-language extraction cases.
Expected meanings were authored from the inputs before executing this dataset;
they were not copied from observed pipeline output. An initial fixture-format
correction removed null optional unit fields; expected meanings were unchanged.
These cases accompany implementation work and are **not an independently
reviewed or held-out benchmark**. `label_provenance` records Codex authorship,
`independent_review: pending`, and `reviewer: null`; evaluation reports preserve
those fields. Independent human labelling/review remains outstanding.

The labels distinguish exact targets, soft thresholds, hard limits, directions,
ambiguous quantities, compatible differing limits, strict interval endpoints,
compound hard intervals, and conflicting/compatible tag requirements. Review
each case's `note` and expected labels against its input meaning, without using
the model's output as the label. Record the independent reviewer and bump the
dataset version if the labels change. Re-evaluate after review; do not claim
independent accuracy from the current results.

```sh
python3 -m decision_service.evaluation \
  --dataset decision_service/fixtures/evaluation/processing_challenge.json \
  --tag structured --output /tmp/processing-challenge-structured.json

python3 -m decision_service.evaluation \
  --dataset decision_service/fixtures/evaluation/processing_challenge.json \
  --semantic-provider ollama --model qwen3:4b-instruct \
  --output /tmp/processing-challenge-live.json \
  --save-evidence-dir /tmp/processing-challenge-evidence
```

On 8 October 2026, `sparse-v7` passed **20/20 structured cases and 64/64
assertions** without a model. The complete rules run passed **20/24 cases and
66/78 assertions**; the four natural-language cases require semantic extraction.
A local Qwen run passed **22/24 cases and 72/78 assertions**, making five model
calls in 60.7 seconds with no operational errors. Saved-evidence replay produced
the same 22/24 results. The two failing comparative preferences were incorrectly
marked hard by the model; clause grounding rejected them and requested
clarification. Both failures and raw model replies remain in the reports;
these labels and prompts were not changed to obtain a passing result.

Frozen [reports and replay evidence](../fixtures/evaluation/recorded/processing_challenge_v1/README.md)
from `sparse-v7` are retained for historical inspection. Current processing
rejects those older artifacts. Current replay evidence is recorded under
`recorded/refactor_v11/challenge/evidence`.

```sh
python3 -m decision_service.evaluation \
  --dataset decision_service/fixtures/evaluation/processing_challenge.json \
  --evidence-dir decision_service/fixtures/evaluation/recorded/refactor_v11/challenge/evidence \
  --output /tmp/processing-challenge-replay.json
```

The historical v7 full challenge run exited `1` because those two cases failed.
Current-version results are documented separately below; failed cases always
remain in the denominator and determine the CLI exit code.

### Configured model

For the repository's Docker Compose setup:

```sh
docker compose -f decision_service/compose.yaml up -d ollama
docker compose -f decision_service/compose.yaml exec ollama ollama pull qwen3:4b-instruct
mkdir -p /tmp/fsd-evaluation
docker compose -f decision_service/compose.yaml run --build --rm -T \
  -v /tmp/fsd-evaluation:/reports \
  preprocessing-demo \
  python -m decision_service.evaluation \
  --semantic-provider ollama \
  --model qwen3:4b-instruct \
  --output /reports/preprocessing-live.json \
  --save-evidence-dir /reports/evidence
python3 -m json.tool /tmp/fsd-evaluation/preprocessing-live.json
```

The mounted directory keeps the report and evidence on the host after the
container exits. Use `--output` rather than redirecting Compose stdout: Docker
build progress can otherwise be written before the JSON and make the report
unreadable. Evaluation exit code `1` still leaves a report with failed cases.

Against an existing Ollama server:

```sh
python3 -m decision_service.evaluation \
  --semantic-provider ollama \
  --model qwen3:4b-instruct \
  --output /tmp/preprocessing-ollama.json \
  --save-evidence-dir /tmp/preprocessing-ollama-evidence
```

Use `--ollama-url` to override the server. The provider can also read
`OLLAMA_BASE_URL`. This command evaluates the whole hybrid pipeline. Supported
rules handle structured questions; the model handles unresolved classification,
open meaning, undeclared scoped synonyms, and suggestions for missing soft facts.

The existing OpenAI provider is also available through
`--semantic-provider openai --model YOUR_MODEL`; it requires `OPENAI_API_KEY`
and makes paid API calls. The mocked provider tests verify report generation and
replay; live development results are documented below.

### Recorded development run

The hardcoding cleanup uses `sparse-v11` (`semantic-v6` for activity input).
Currency and duration tests cover non-SGD budgets, declared minor-unit precision,
exact large decimals, durations above a year, strict endpoints and scenario limits.
The refactor was checked with the previously recorded model replies: **34/34**
development cases, **24/24** challenge cases and **8/10** follow-up cases retain
their labelled outcomes. These are recorded-response regression results, not a
new live-model accuracy run. Fresh evidence was emitted by the current pipeline;
older evidence versions were not relabelled as current artifacts.
[Regression reports and current replay evidence](../fixtures/evaluation/recorded/refactor_v11/README.md)
preserve the distinction and the two known model failures. Historical live runs
below retain their original versions and results.

On 8 October 2026, the finalized natural-language changes in `sparse-v10` with
`scoped-labels-v3` passed **34/34 development cases and 185/185 assertions**,
and **24/24 challenge cases and 78/78 assertions**. The new
[language_followup.json](../fixtures/evaluation/language_followup.json) passed
**8/10 cases and 21/24 assertions**. All three saved-evidence replays reproduce
the live results with no operational errors. The development run took 87.8
seconds/12 calls; challenge 57.1 seconds/5 calls; follow-up 98.4 seconds/10 calls.

Comparative repairs use supported English grammar within the item's evidence
clause, after the model selects a typed criterion. Explicit hard questions and
real requirements are not softened. Single-token category labels use direct
scoped canonicalization rather than asking extraction to infer obligation.
The synonym prompt assesses each alternative separately and distinguishes clear
new meanings from genuinely ambiguous labels. It contains no runtime global
programming/coding alias table.

The follow-up failures are an incoherent hiking/outdoor assessment (clarification)
and an incorrect noisy/busy equivalence (estimated model preference). Both
remain in the report and denominator. The follow-up labels were authored before
first execution, then used in development; they are not held-out or independently
reviewed data. Independent human review is still pending.

[Final reports, intermediate failures and replay evidence](../fixtures/evaluation/recorded/language_v10/README.md)
are preserved, including an intermediate provider timeout. No failed labels were
changed to obtain a passing result. Historical runs below use older processing
versions and are not current-pipeline accuracy claims.

On 8 October 2026, `sparse-v7` with `qwen3:4b-instruct` passed **33/34 cases
and 183/185 assertions** on dataset version 5 in 77.3 seconds, making 12 model
calls with no operational errors. Replay reproduced the same result. The model
again missed undeclared programming/coding equivalence; this regression was
preserved rather than rerunning until it passed. The rules baseline remains
23/34 cases and 148/185 assertions, including 22/22 structured cases.
The [live report](../fixtures/evaluation/recorded/development_v5/live.json)
and [replay report](../fixtures/evaluation/recorded/development_v5/replay.json)
retain the failure and raw reply. Historical dataset/version runs below are not
current-pipeline accuracy claims.

On 7 October 2026, the `sparse-v6` pipeline with `qwen3:4b-instruct` passed
**34/34 cases and 185/185 assertions** on dataset version 4. The final run took
**64.1 seconds** and made **12 model calls**. Saved-evidence replay also passed
all 34 cases. The three structured canonicalization cases pass without a model.

Earlier runs missed the undeclared programming/coding synonym. A full run also
showed an incorrect red/blue equivalence for a selected form choice; declared
choices are now registered as established labels and bypass model remapping.
The model prompt was clarified to use scoped meaning, type, and unit. The final
run resolved both synonyms and kept vegan/vegetarian distinct, but earlier synonym
failures remain evidence of model variability. Passing this development corpus
does not establish repeat-run stability or accuracy on unseen labels.

Canonicalization uses declared aliases first, with optional model assessments
for remaining labels. Sources, original wording, and evidence statuses remain
visible; no assessment retrieves or confirms an option fact. Target validation
checks structure and references, not semantic truth.

#### Dataset version 3

On 7 October 2026, the `sparse-v5` pipeline with `qwen3:4b-instruct` passed
**28/28 cases and 158/158 assertions** on dataset version 3. The first run passed
26/28 cases: the model mislabelled a strict numeric bound and a comparative
direction. Literal numeric evidence checks and the numeric intent prompt were
updated; a fresh live run passed all cases. Saved-evidence replay also passes.
The final run took **73.4 seconds** and made **9 model calls**.

The ten added cases cover multiple criteria per answer, directional and range
preferences, strict budget limits, different member importance, ordinal
comparisons, and cycles. The report checks these fields independently of JSON
schema validity. Model interpretations remain estimated; inferred hard meanings
still require confirmation. These are development examples used to improve the
implementation and do not establish accuracy on unseen inputs.

#### Previous dataset

On 6 October 2026, the local `qwen3:4b-instruct` pipeline passed **18/18 cases and
108/108 assertions** in **27.4 seconds**, using 6 model calls. The earlier
integration passed 3/18 cases in 202.3 seconds and returned `invalid_input` in
13 cases. The final run's one `invalid_input` result is the deliberately
conflicting-budget example; all five expected member-clarification cases pass.

This improvement followed routing changes, deterministic mappings, clause-level
requirement checks, and date-year checks. Dataset version 2 replaces exact equal
automatic-weight assumptions with normalization checks; leader weights remain
exact. The earlier report had 109 checks and version 2 has 108, so assertion
percentages across those versions are not a direct comparison.

Saved-evidence replay also passes all 18 cases. These are development examples
used to diagnose the changes. They do not establish generalization to unseen
decisions, repeat-run stability, or accuracy of Qwen alone. Add independently
reviewed held-out examples before making those claims.

### Replay

```sh
python3 -m decision_service.evaluation \
  --evidence-dir /tmp/preprocessing-ollama-evidence \
  --output /tmp/preprocessing-replay.json
```

Each selected case needs its own `case_id.json` evidence object. The pipeline
validates snapshot IDs and processing version. Missing, stale, or malformed
evidence produces a failed case; a missing file never silently falls back to rules.
Generic processing now uses `sparse-v11`. Regenerate earlier semantic artifacts.
Canonicalization records include frozen assessments, declared aliases, and whether
model equivalence was enabled; a replay rejects changed declarations or missing
assessments for a model-enabled run.
An evidence directory cannot be combined with a live provider. Hybrid runs save
an empty assessment set with `model: null` for generic cases resolved entirely
by rules. These records replay those same rules with frozen snapshot IDs/version.
Rejected model calls may leave cases without accepted artifacts; their replies
remain in the report's `model_calls` diagnostics.

Reports and evidence can contain member values and should be kept private when
evaluating real responses. The report omits full input snapshots.

## Read the report

The JSON report includes:

- Mode (`rules`, `live`, or `replay`), provider model, UTC timestamp, dataset
  version/hash, and per-case processing version/evidence model.
- Passed/total cases. A case passes only when every assertion passes and no
  operational error occurs.
- Passed/total assertions, grouped by domain and dimension.
- Failure paths, expected values, actual values, and missing/unexpected rows.
  Metrics distinguish missing paths from value mismatches.
- Every case's validation issues and model calls, including replies subsequently
  rejected by validation. Call records contain method, subject, response, and time;
  API transport credentials are not recorded.
- Operational errors and elapsed time. Exceptions and provider outages remain
  in the case denominator.

Dimensions are `classification`, `mapping`, `weights`, `extraction`,
`constraints`, `facts`, `clarification`, and `status`. Assertion accuracy is a
fraction of labelled checks; it is not entity precision/recall, weight calibration,
or an estimate of accuracy in production. Cases have different numbers of checks,
so read case accuracy alongside dimension results. Durations include all calls
within a case, not just model inference.

Progress and the summary go to stderr. JSON goes to stdout or `--output`.
Exit codes are `0` for every selected case passing, `1` for evaluation failures,
and `2` for bad dataset/configuration or report I/O. A provider failure during
evaluation appears in the report and returns `1`.

## Add labelled cases

Each case includes a unique lowercase `case_id`, `domain`, `tags`, complete
`planning` and `responses` snapshots, and nonempty `assertions`. Use a new
snapshot ID/revision when changing inputs; old semantic artifacts must not be
reused for modified snapshots. Increment `dataset_version` when labels change.

An assertion has exactly four fields:

```json
{
  "dimension": "constraints",
  "path": "/preparation/constraints",
  "op": "rows",
  "value": [{
    "source_question_id": "budget",
    "attribute_id": "max_cost",
    "required_value": "2000",
    "constraint_rule": "maximum_v1",
    "unit": "SGD",
    "confirmation_status": "confirmed"
  }]
}
```

Paths use JSON pointers; escape `/` as `~1` and `~` as `~0` in keys. A missing
path fails even when the expected value is null.

| Operator | Meaning |
| --- | --- |
| `equals` | Exact value, including ordered lists and object fields; booleans differ from numbers |
| `approx` | Finite numeric value within an absolute tolerance of `1e-9`; used for normalized weights |
| `normalized_weights` | Active soft-question IDs match the labelled list, weights are finite/nonnegative and sum to 1, and other roles have no scoring weight |
| `rows` | Unordered list with exactly one actual row per labelled row; labelled fields must match, extra fields within a row are allowed |
| `contains_rows` | One distinct actual row per label, allowing extra rows |
| `absent_rows` | No actual row may match any of the labels |

Nested objects in row labels also match only their labelled fields. Lists within
a row label remain exact and ordered, including normalized tag sets. Exact row
checks on constraints and preferences catch extra interpretations as well as
missing ones. For issues, use `contains_rows` to allow additional valid warnings.
Use `rows` with `[]` to assert that no entries exist.

Write expected meanings independently of observed output. Label a hard
requirement's confirmation status as well as its value/rule. Pair identical
questions in different decision contexts to check relevance. Preserve difficult
failing cases when improving the extractor. Separate future held-out examples
from examples used to tune rules/prompts.

## Verification

```sh
python3 -m unittest discover -s decision_service/tests -v
```

The evaluation tests verify error detection, row matching without reuse, label
validation, snapshot isolation, continued execution after errors, CLI exit codes,
and saved evidence replay. Generic ranking and external fact retrieval remain
outside this evaluation's scope.
