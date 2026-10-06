# Decision Service contracts

The execution schema is `activity-v2`; preprocessing uses `semantic-v5`.
`decision_service/contract.py` validates the same handoff before preprocessing
returns `ready` and before the algorithm runs. Old execution payloads must be
regenerated from their planning and response snapshots.

For generic question inference, typed outputs, and runnable input/output examples,
see [Preprocessing flow](FLOW.md).

## Input and processing flow

1. **Planning snapshot:** round/revision/snapshot IDs, exact roster, time zone,
   currency, decision question, activities, and question definitions.
2. **Response snapshot:** matching round/revision, response snapshot ID, member
   response status, and answers with unique question IDs and answer IDs.
3. **Candidate generation:** expand each activity's duration and windows into
   concrete start/end candidates on a 30 minute grid. Preserve supplied fact
   types, units, sources, and evidence status.
4. **Answer extraction:** normalize structured availability, budgets, ratings,
   and flags locally. The rule extractor handles its declared vocabulary;
   semantic questions use a configured provider or frozen model evidence.
5. **Semantic normalization:** map a resolved model value through the question's
   explicit `semantic_binding`. Unmapped meanings require clarification.
   Model requirements need confirmation of the actual mapped attribute/value.
6. **Weighting:** keep hard questions unweighted. Normalize leader weights and
   automatic question relevance across soft questions. Several preferences
   extracted from one question share its weight.
7. **Validation:** check schema, references, roster, duplicates, conflicts,
   confirmation, types, units, finite weights, utilities, and policies.
8. **Execution:** check hard feasibility, score applicable soft answers, apply
   the group objective, and use cost/time/ID tie breakers. Return aggregate
   scores and explanation codes without answer text or member score details.

```python
from decision_service.preprocessing import preprocess
from decision_service.algorithm import run_decision

prepared = preprocess(planning_snapshot, response_snapshot, policy=policy)
if prepared["status"] == "ready":
    result = run_decision(prepared["algorithm_input"], run_id="decision-123")
    public_response = result.as_dict()
```

Preprocessing statuses:

| Status | Meaning |
| --- | --- |
| `ready` | Structurally valid execution input with normalized member answers |
| `needs_clarification` | Missing, ambiguous, unmapped, or unconfirmed member meaning |
| `provisional` | Sparse preparation requiring an execution adapter |
| `invalid_input` | Malformed snapshots, mappings, facts, or policy |
| `upstream_unavailable` | Configured semantic service failed |

Only `ready` has a non-null `algorithm_input`. Ready does not promise a feasible
winner: unknown facts are valid data and can block execution. Model evidence
and interpreted meaning are separate, private preprocessing outputs.

## Execution handoff

```text
context: schema_version, activity_ids, round/snapshot IDs, versions,
         timezone, semantic_model, semantic_artifact_id
criteria: [{attribute_id, value_type, unit}]
candidates: [{candidate_id, activity_id, start_at, end_at, currency,
              estimated_cost_minor, facts, ...}]
participants: [{participant_id, response_status, is_required_for_decision}]
constraints: [{participant_id, availability, budget, required_attributes,
               candidate_flags, answer_sources}]
preferences: [normalized preferences]
scoring_model: {questions, group_objective, ranking_policy, missing_value_policy}
```

The criterion registry comes from supplied facts and declared question
mappings. It is not a list of countries or decision domains. Initial utilities
support ratings, scalar attribute equality, and explicit indifference. Integer,
number, category, and boolean values are supported; numeric equality is not a
numeric distance or threshold utility. All facts for a criterion must have the
same type and unit. Unit conversion and external fact gathering are not
implemented.

## Candidate facts

Planning activities accept `attributes` with optional type, unit, status, and
source. Existing yes/no/unknown inputs are accepted; legacy `unknown` becomes
`value: null, status: unknown`. The execution output uses typed `facts`:

```json
{
  "attribute_id": "noise_level",
  "value": "quiet",
  "value_type": "category",
  "unit": null,
  "status": "confirmed",
  "source": "venue_information"
}
```

Costs use `attribute_id: estimated_cost`, `value_type: integer`, and currency
minor units such as `SGD_minor`. `2500` means SGD 25.00. The candidate's
`estimated_cost_minor` summary must equal its typed cost fact. Planning can
supply `cost_status` and `cost_source`. Supplied frozen values default to
`confirmed` with source `planning_service`; this treats Planning as the
source of record, and does not mean preprocessing independently verified them.
Model guesses must be explicitly supplied as `estimated`.

Unknown cost is null, never zero. For a limited budget, missing or estimated
cost makes the candidate unresolved. Unlimited budgets do not need a cost
check. Hard attribute checks require confirmed facts. Soft equality can use
confirmed or estimated facts; unknown or absent facts remain unresolved.

## Preferences and hard requirements

Every preference has participant, question and answer IDs, source type, evidence,
resolution status, scope, and utility rule:

```json
{
  "participant_id": "p1",
  "source_question_id": "q_environment",
  "source_answer_id": "answer-123",
  "source_type": "member_response",
  "evidence": "somewhere quiet",
  "kind": "attribute_preference",
  "attribute_id": "noise_level",
  "preferred_value": "quiet",
  "utility_rule": "attribute_match_v1",
  "scope": "all",
  "status": "confirmed"
}
```

Scopes are `all`, `activity` with `activity_id`, `candidate` with `candidate_id`,
and `scenario` with `scenario_id`. A scenario preference requires candidates
that declare that scenario ID. Ratings need a target and use `rating_v1` with
an integer 0–4, normalized as rating/4. Explicit no preference becomes
`kind: indifferent`, `utility_rule: neutral_v1`, `status: explicitly_indifferent`
and utility 0.5. A rating of 2 remains a rating; it is distinguishable from
explicit indifference. Missing responses are never converted to either.

Hard attributes contain `attribute_id`, `required_value`, the same provenance,
`participant_id`, `status: confirmed`, and `confirmation_status: confirmed`.
Direct member requirements extracted by the rule parser are self-reported
confirmed constraints. Model-derived requirements need a reviewed value.

## Semantic question mapping

A semantic question declares how model value labels map into the execution
registry. Any attribute ID can be declared with a supported scalar type:

```json
{
  "question_id": "q_access",
  "label": "What access do you need?",
  "kind": "semantic_requirement",
  "semantic_binding": {
    "attribute_id": "step_free_access",
    "value_type": "category",
    "values": {"ramp_required": "yes", "no_requirement": null}
  }
}
```

After reviewing the interpretation, the response answer must include
`confirmed_requirement: {"attribute_id": "step_free_access", "required_value": "yes"}`.
The confirmation must match this mapped meaning and value type. Include the
binding's `unit` in `confirmed_requirement` when a unit is declared. Null means explicit
indifference for a soft binding and no requirement for a confirmed hard binding.
A missing mapping is a clarification issue, not a text-based scoring rule.
The model receives the binding and must return a supported label or unresolved.

## Scoring and group policy

Each soft question declares `weight`, `utility_rule`, `aggregation`,
`missing_value_policy: unresolved`, `criteria`, and `is_hard_constraint: false`.
`direct` needs exactly one applicable answer; `average` combines distinct
attribute utilities before applying the question's weight. Unsupported rules,
conflicting overlapping scopes, and mixed indifference/other answers are
rejected. Zero-weight questions do not require option evidence for scoring.

The default policy is:

```json
{
  "mode": "maximin_then_average",
  "minimum_score_weight": 0.6,
  "average_score_weight": 0.4,
  "fairness_weight": 0.0
}
```

Pass overrides through `preprocess(..., policy={"group_objective": {...}})`.
`maximin_then_average` sorts by minimum member score, then average; its
coefficients do not change that lexicographic order. `weighted_fairness` uses:

```text
group_score = (minimum_weight * minimum + average_weight * average)
              / (minimum_weight + average_weight)
              - fairness_weight * population_variance(member_scores)
```

It sorts by group score, then minimum and average. Both use lower cost, earlier
start instant, and stable candidate ID to break ties. Unknown costs sort last.
The contract validates the declared sort order against the objective.

## Algorithm output

`run_decision` returns `ranked`, `blocked`, `no_feasible_candidate`, or
`invalid_input`, along with run/policy/algorithm versions. A ranked result
contains candidate IDs, ranks, minimum and average member scores, group score,
fairness penalty (population variance), estimated cost, start time, and a Pareto
frontier across minimum/average/cost. Candidate results contain feasibility
and aggregate explanation codes.

Any unresolved candidate blocks the final recommendation because it could
outperform the currently scoreable candidates. Examples are `MISSING_COST`,
`ESTIMATED_COST`, `MISSING_OPTION_FACT`, `MISSING_SOFT_OPTION_FACT`, and
`MISSING_SOFT_ANSWER`. Definite hard failures exclude the candidate. An empty
candidate inventory returns `no_feasible_candidate`.

## Sparse preparation

Planning with `options` instead of `activities` selects `sparse-v3`. It accepts
leader-written questions, option names/descriptions/sourced facts, and member
answers. It produces criterion classifications, normalized budgets/durations,
interpreted preferences, missing criteria, hypothetical tags, and scenario
requests when availability and duration are supplied.
The processing version is `sparse-v4`, separate from the handoff schema.
Supported rules run before semantic classification; comparison declarations
are generated in code from supplied facts and validated question roles.

The partial data lives under `preparation`; `algorithm_input` is null.
`preparation.status` distinguishes completed preprocessing (`ready`), missing
information, and member clarification. Generic questions now receive automatic
typed mappings, declared comparison rules, normalized preferences/constraints,
provenance, and typed fact requests. Facts determine criterion types; the model
cannot change their units or invent numeric scales. Member answers are excluded
from question weighting. Negative preferences carry explicit `polarity`.

The outer result remains `provisional` with `EXECUTION_ADAPTER_REQUIRED` until
the generic algorithm implements this packet. Passing `sparse-v2` or `sparse-v3`
directly to the current algorithm returns `blocked` with
`SPARSE_HANDOFF_NOT_SUPPORTED` before activity validation. The generic and
activity comparison declarations are separate contracts; new numeric/tag rules
are not supported by the activity algorithm.

## Verification

From the `FSD` repository root:

```sh
python3 -m unittest discover -s decision_service/tests -v
python3 -m decision_service.algorithm decision_service/fixtures/preprocessing/expected_algorithm_input.json
```

`tests/test_handoff.py` covers normalization and confirmation;
`tests/test_algorithm.py` covers contract rejection and execution, including
semantic answers changing the result. Provider tests use mocked transport;
this suite does not measure live model extraction accuracy.
