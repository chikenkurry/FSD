# Preprocessing flow

Preprocessing turns the plan and member answers into typed data and comparison
declarations. It does not calculate scores, rank options, or retrieve external
facts. The generic path now uses `sparse-v3`; the activity/time execution path
continues to use `activity-v2`.
Generic processing is versioned separately as `sparse-v4`; older model artifacts
must be regenerated before replay.

## Function

```python
from decision_service.preprocessing import preprocess

result = preprocess(
    planning_snapshot,
    response_snapshot,
    policy=None,
    semantic_provider=None,
    semantic_evidence=None,
)
```

Use `planning.options` for a generic decision. Use `planning.activities` for
an existing activity/time round. The service IDs identify immutable snapshots;
callers must supply matching round IDs and option revisions.

## Input

### Planning snapshot

| Field | Purpose |
| --- | --- |
| `round_id`, `option_revision`, `option_snapshot_id` | Identify the frozen plan |
| `decision_question` | The decision goal used for semantic classification |
| `roster` | Exact list of members whose responses are required |
| `options` | Names, or objects with option ID, title, description, and sourced facts |
| `questions` | Question IDs, ordinary labels, and optional choices/formats |
| `currency`, `cost_scope` | Required when asking for a monetary limit |
| `context` | Optional decision details; no required travel-specific fields |

A fact uses `{criterion, value, status, source, unit?, value_type?, context?}`.
Known types can be inferred from supplied scalar values or text-tag lists.
An explicit unknown fact needs a null value and declared type. Descriptions and
model-suggested tags do not become confirmed facts.

Questions do not require a `kind` or manual semantic binding on this path.
Supported form declarations are `text`, `choice`, `multi_choice`, `number`,
`boolean`, and `date_intervals`. Ordinary numeric/boolean values and declared
choice IDs are accepted in the answer envelope. A leader can override role,
criterion, relevance, weight, or mapping when needed.

### Response snapshot

```json
{
  "round_id": "product-1",
  "option_revision": "1",
  "response_snapshot_id": "product-responses-1",
  "participants": [{
    "participant_id": "p1",
    "response_status": "complete",
    "answers": [
      {"answer_id": "p1-budget", "question_id": "budget", "value": 1500},
      {"answer_id": "p1-battery", "question_id": "battery", "value": "12 hours"},
      {"answer_id": "p1-usage", "question_id": "usage", "value": ["Coding", "Design"]}
    ]
  }]
}
```

Answer IDs are preferred. When omitted, preprocessing generates a stable ID
from response snapshot, member, and question IDs. It rejects duplicate IDs and
unknown/repeated questions.

See [planning_generic.json](../fixtures/preprocessing/planning_generic.json)
and [response_generic.json](../fixtures/preprocessing/response_generic.json)
for a complete example. All prices and specifications in these fixtures are
synthetic test data.

## Steps between input and output

1. **Validate snapshots and roster.** Check IDs, revisions, member status,
   duplicate records, supported formats, facts, currencies, and budget scope.
2. **Build the fact registry.** Identify each criterion's type and unit from
   supplied facts. Normalize categories/tags with case folding and whitespace
   normalization. Monetary amounts remain exact decimal strings in major units.
3. **Interpret questions.** Honor explicit leader definitions, then use supported
   rules for budget/date/duration wording and questions naming a supplied fact
   criterion. Ask the provider about unresolved meanings against the decision
   goal and supplied facts. Generic preference wording alone does not identify
   an attribute. Model classifications cannot make an ordinary target hard
   without explicit limit wording; hard/informational relevance is derived as 0.
   Ambiguous or unfamiliar questions without a provider remain unclassified.
4. **Generate mappings.** Choose declarations from criterion type and question
   role in application code. The model does not declare mappings. For example:
   numeric target, tag overlap, categorical equality, or a
   maximum/minimum hard limit. Units must agree with the fact registry. A numeric
   target scale comes from confirmed option values, offered duration choices,
   or an explicit leader mapping. The model cannot invent a scale.
5. **Resolve question weights.** Use supplied leader weights or question
   relevance. Repeated automatic topics share relevance, and soft weights are
   normalized. Hard and informational questions have no scoring weight. Member
   answers are excluded from this stage. These weights describe question
   usefulness, not a member's personal importance ratings.
6. **Extract answers.** Parse exact dates, numbers/units, budget values including
   `2k`, choices, booleans, and explicit indifference locally when possible.
   A semantic provider extracts other text into grounded interpretations,
   preserving preferred versus avoided values. Evidence must occur in the answer.
   A hard interpretation needs requirement wording in its own clause; an unrelated
   clause cannot turn a preference into a requirement. Vague dates without a
   stated year request clarification before any model date extraction.
7. **Compile typed answers.** Emit preferences and hard constraints with rule,
   unit, source question/answer IDs, evidence, and resolution status. A model
   interpretation of a hard requirement or available date range needs typed
   confirmation. Individual evidence excerpts are preserved; merged tag meanings
   carry `evidence_excerpts` when several excerpts support the record. An optional
   unanswered scoring question stays unresolved.
8. **Describe missing information.** Request facts by option, criterion, type,
   unit, source question, and priority. For date/duration decisions, form scenario
   requests and request costs with the relevant dates, duration, and budget scope.
9. **Validate the preparation.** Check declarations, references, units,
   normalized answers, and conflicts. Return the typed packet plus actionable
   issues and frozen model evidence for replay.

The semantic provider is optional. Arbitrary wording still needs a configured
provider or saved evidence when rules cannot interpret it. Unit conversion,
external fact collection, and fuzzy tag matching are not implemented.
Unsupported numeric negative constraints require
clarification rather than being converted to an incorrect limit.

The [evaluation runner](EVALUATION.md) now measures labelled development cases
using rules, a configured provider, or saved evidence. A live development run is
recorded in the evaluation documentation; accuracy on unseen inputs is unmeasured.

## Output

The generic result separates preprocessing completion from algorithm support:

```json
{
  "status": "provisional",
  "algorithm_input": null,
  "preparation": {
    "status": "ready",
    "context": {"schema_version": "sparse-v3"},
    "criteria": [],
    "candidates": [],
    "participants": [],
    "constraints": [],
    "preferences": [],
    "scoring_model": {},
    "fact_requests": [],
    "scenario_requests": []
  },
  "issues": [{"code": "EXECUTION_ADAPTER_REQUIRED"}],
  "semantic_evidence": null
}
```

This sketch omits field details. The complete frozen packet is
[expected_generic_preparation.json](../fixtures/preprocessing/expected_generic_preparation.json).

`preparation.status` means:

| Status | Meaning |
| --- | --- |
| `ready` | Active criteria, member answers, and required evidence are prepared |
| `needs_information` | Option facts, mappings, semantic provider, or context are missing |
| `needs_clarification` | Member answers or interpreted hard values need attention |

The outer `status` remains `provisional` for generic decisions, or
`needs_clarification` when member review is needed. Malformed inputs produce
`invalid_input`; a configured provider failure produces `upstream_unavailable`.
The existing algorithm handles activity/time input and cannot execute this
schema yet, so `algorithm_input` is null even when preparation is ready.

For the product fixture, the output includes:

- A confirmed `max_cost <= "1500"` constraint in USD major units.
- A battery-life target of `12` hours, with `numeric_target_v1` and scale `3`.
- Preferred usage tags `["coding", "design"]` with `tag_overlap_v1`.
- Battery and usage question weights of `0.5` each.
- No required dates, duration, or scenario requests.

A normalized preference has this shape:

```json
{
  "participant_id": "p1",
  "source_question_id": "battery",
  "source_answer_id": "p1-battery",
  "source_type": "member_response",
  "evidence": "12 hours",
  "kind": "attribute_preference",
  "attribute_id": "battery_life",
  "value_type": "number",
  "preferred_value": 12,
  "unit": "hours",
  "scope": "all",
  "polarity": "prefer",
  "utility_rule": "numeric_target_v1",
  "status": "confirmed"
}
```

A model-derived hard answer carries `confirmation_status: needs_confirmation`.
After review, the response can include:

```json
{
  "confirmed_requirement": {
    "attribute_id": "usage_tags",
    "required_value": ["coding"],
    "constraint_rule": "contains_all_v1",
    "unit": null
  }
}
```

It must match the actual interpreted value, rule, and unit. Confirmed constraints
are kept separate from soft preferences. The packet and semantic evidence contain
private member data; public recommendation responses should expose aggregate
explanations instead.

## Responsibility of the generic algorithm

Your teammate needs to implement the declarations in this packet:

- `attribute_match_v1`: scalar equality.
- `tag_overlap_v1`: fraction of desired tags supported by option tags.
- `numeric_target_v1`: `max(0, 1 - abs(actual - target) / scale)`.
- `neutral_v1`: explicit indifference, utility `0.5`.
- `maximum_v1`, `minimum_v1`, `equals_v1`, `not_equals_v1`,
  `contains_all_v1`, `excludes_all_v1`, and `date_overlap_v1`: hard checks.

For soft `polarity: avoid`, invert the base match utility. Several preferences
from one question share its weight through the declared aggregation. A date
check requires the candidate date interval to fit the member's available
intervals; it must not accept a candidate merely because the intervals touch.
Unknown facts do not prove hard feasibility. The declared group objective and
missing-value policy remain part of the handoff. These are proposed generic
comparison semantics, not implementations in the current activity algorithm.

## Run and verify

From `FSD`:

```sh
python3 -m decision_service.preprocessing \
  --planning decision_service/fixtures/preprocessing/planning_generic.json \
  --responses decision_service/fixtures/preprocessing/response_generic.json

python3 -m unittest discover -s decision_service/tests -v
```

Implementation responsibilities are split across `generic_mapping.py` (types and
mappings), `generic_answers.py` (extraction), `generic_preparation.py` (compilation
and validation), and `sparse.py` (snapshots and scenario orchestration). Provider
transport tests are mocked; the suite does not measure live extraction accuracy.
Use `python3 -m decision_service.evaluation` for the cross-domain labelled report.
