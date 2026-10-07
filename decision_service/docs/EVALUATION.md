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
concepts. These remain authored development cases, not independent held-out data.
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
Generic processing now uses `sparse-v6`. Regenerate earlier semantic artifacts.
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
