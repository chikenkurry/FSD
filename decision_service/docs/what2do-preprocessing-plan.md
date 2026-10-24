# What2Do: your Decision Service preprocessing plan

This document records the initial implementation plan. The current executable
interface and behavior are documented in [Decision Service contracts](algorithm-input-shape.md).

## 1. Your goal

Build the part of Decision Service that converts structured answers and open-text answers into a validated input for your teammate's matching algorithm.

Your deliverable is a function, its input/output schemas, and example data. You can build and test these with mock JSON files before the other services are ready.

```text
Questions + activity facts + member answers + optional leader weights
                                |
                        YOUR PROCESSING
              Interpret questions and open answers
              Validate and normalize the extracted values
              Resolve weights and generate candidate times
                                |
                       EvaluationInputV1
                                |
                    TEAMMATE'S MATCHING
              Check constraints and calculate candidate scores
              Rank feasible choices and explain the results
```

This plan follows your updated requirements: both structured and open questions, semantic extraction, and optional leader-supplied question weights. These extend the earlier documents, which proposed fixed fields and deferred open-text interpretation. The policies below are proposed implementation defaults for discussion with your teammate, not additional rubric requirements.

## 2. Agree on the division of work

| Work | Primary owner | Concrete output |
| --- | --- | --- |
| Define the input/output contract and meaning of each field | Both | Versioned schema and shared examples |
| Map questions to supported criteria | You | Question definitions with criterion, value type, and scoring rule reference |
| Read structured fields and extract meaning from open answers | You | Typed facts, constraints, preferences, and unresolved issues |
| Normalize money, dates, availability, and answer values | You | Consistent machine-readable values |
| Apply the agreed question-weight policy | You | Normalized weights and their source |
| Generate activity/start/end candidates | You | Candidate list with stable IDs |
| Evaluate candidates against every member's constraints | Teammate | Feasible, infeasible, or unresolved candidate results |
| Convert preferences into candidate scores and rank choices | Teammate | Scores, ordering, and reason codes |
| Connect preprocessing to the matching function | Both | One working local pipeline |

API endpoints, persistence, result UI, and deployment remain Decision Service work, but should be assigned explicitly. They are not prerequisites for your first preprocessing prototype.

## 3. What you receive

Start with three mock JSON files:

| File | Contents |
| --- | --- |
| `mock_options.json` | Plan/round IDs, approved roster, timezone, activities, costs, durations, windows, known activity attributes, question definitions, optional leader weights |
| `mock_responses.json` | Member IDs, submission/revision information, structured answers, and open-text answers with their question IDs |
| `expected_evaluation_input.json` | The manually checked output that your processing should produce |

Each answer must remain attached to its question. For example, “30” means something different under “Maximum spend in SGD?” and “Maximum travel time in minutes?”. Extract using the question, its declared units, the answer, and relevant plan context together.

The later integration should obtain immutable option and response snapshots from Planning and Participation. Extend their contracts to include questions, weights, and the open answers intended for decision processing. Keep optional private notes separate from answers that are used by the algorithm.

## 4. What you produce

Use one agreed interface:

```python
preprocess(option_snapshot, response_snapshot, policy) -> PreprocessingResult

# Your teammate implements:
evaluate(evaluation_input) -> RecommendationResult
```

`PreprocessingResult` contains `status`, `issues`, and an optional `evaluation_input`:

- `ready`: the contract is valid and all required member answers are resolved. Some candidate facts can still be explicitly unknown; the matcher must handle those.
- `needs_clarification`: a required answer, question meaning, or weight configuration cannot be resolved. Return specific issues and no authoritative evaluation input.
- `invalid_input`: malformed data, unsupported schema, mismatched snapshot references, or inconsistent IDs prevent processing.

Do not label missing information as “no feasible option.” Only the matcher can determine incompatibility from evaluated candidates.

`EvaluationInputV1` should contain:

| Field | Purpose |
| --- | --- |
| `schema_version` | Version of the handoff format |
| `input_refs` | Plan, round, option/response snapshot IDs, and revisions |
| `processing_versions` | Extraction, normalization, and weight-policy versions |
| `timezone`, `currency` | Interpretation and display context |
| `roster` | Exact member IDs to include |
| `questions` | Question IDs, mapped criteria, value types, weight information, and utility-rule references |
| `activities` | Known costs, duration, attributes, and explicit unknown facts |
| `candidates` | Candidate ID, activity ID, start, end, and option revision |
| `members` | Normalized availability, budgets, hard requirements, and soft preferences |

Keep extraction evidence in a separate private record, linked by answer/extraction IDs. The public recommendation response should contain aggregate explanations rather than raw answers or individual caps.

### Example of the semantics you extract

This is an excerpt from one member's processed data, not the complete `EvaluationInputV1` object:

```json
{
  "member_id": "m2",
  "constraints": [
    {
      "question_id": "q_budget",
      "criterion": "cost_per_person",
      "operator": "lte",
      "value": 3000,
      "unit": "SGD_minor",
      "source_answer_id": "answer_12"
    },
    {
      "question_id": "q_requirements",
      "criterion": "vegetarian_option",
      "operator": "eq",
      "value": true,
      "source_answer_id": "answer_13"
    }
  ],
  "preferences": [
    {
      "question_id": "q_environment",
      "criterion": "environment",
      "preferred_value": "indoor",
      "utility_rule": "categorical_match_v1",
      "source_answer_id": "answer_14"
    }
  ]
}
```

This could come from a structured budget answer of SGD 30, “I must have a vegetarian option,” and “I prefer an indoor venue.” Your teammate compares these values with candidate facts. An activity's name alone does not establish whether it has vegetarian food or is indoors.

## 5. Build the processing stages

### Stage A: interpret the questions

Start with a controlled set of criteria: availability, per-person budget, activity rating, dietary/accessibility requirements, environment, and noise preference. Define allowed values and units for each.

Open questions can map to these criteria. For example, “What sort of atmosphere would you enjoy?” may collect environment and noise preferences. An arbitrary new question needs a declared or reviewed mapping before it affects ranking; an LLM-generated label alone is insufficient.

Store a `utility_rule` for each soft criterion. This defines how a preference is compared with activity facts. Both of you must agree on these rules; your teammate implements their scoring.

### Stage B: extract the answers

Use direct field mappings for structured answers. For open answers, extract the criterion, value, units, whether it is a requirement or preference, and the answer text supporting that interpretation.

| Answer | Expected interpretation |
| --- | --- |
| “My maximum is $30.” | Budget cap of 3000 SGD minor units, given an SGD question/context |
| “No spending limit.” | Explicit unlimited budget |
| “I must have step-free access.” | Hard requirement for `step_free_access = true` |
| “I would prefer somewhere quiet.” | Soft noise preference |
| “I don't need vegetarian food.” | No vegetarian requirement; preserve the negation |
| “Something cheap.” | Numeric budget unresolved |
| “Friday evening.” | Exact availability unresolved unless the form explicitly defines that period |

Use the question's declared meaning when interpreting answers. An answer to a preference question may still state a hard requirement; preserve that distinction and validate it rather than forcing every answer into a weighted preference.

A practical implementation order is a small rules-based extractor for clear phrases, followed by an extractor that uses an LLM to return the same typed schema. The LLM suggests interpretations; validation code checks fields, supported criteria, units, references, and contradictions. Treat answer text as data, including any text that attempts to give instructions to the extractor.

### Stage C: validate and normalize

- Verify the exact roster, round, and revisions. Do not silently drop a missing member.
- Store money in integer minor units. Keep zero, unlimited, and missing distinct.
- Convert times to unambiguous instants and retain the plan timezone. Resolve relative dates against explicit plan dates, not the machine's current date.
- Merge overlapping or adjacent availability intervals. Use half-open intervals `[start, end)` consistently and do not bridge genuine gaps.
- Validate ratings against the declared scale. Explicit no-preference may map to neutral; missing answers stay missing.
- Preserve unknown activity facts. A missing price is not free; an unknown attribute is not false.
- Report conflicting answers, such as a structured cap of $20 and an open answer stating a maximum of $50. Do not choose one silently.

For uncertain extraction, return an issue with an answer ID, reason, and a concrete clarification prompt. An extractor's self-reported confidence is not proof that the interpretation is correct. Proposed product rule: show extracted hard constraints for member review before submission; unresolved required meaning blocks final evaluation.

### Stage D: resolve question weights

Weights express importance among soft questions. Hard constraints remain mandatory checks; their weights are `null`.

Use the following baseline policy:

1. If the leader supplies weights for every soft question, accept finite nonnegative values and normalize them: `weight(q) = supplied(q) / sum(supplied weights)`.
2. If the leader supplies none, assign equal weights: `weight(q) = 1 / number_of_soft_questions`.
3. If only some are supplied, request the missing weights or an explicit switch to defaults. Do not silently mix scales.
4. Reject an all-zero weight set. If there are no soft questions, skip weighting and return feasible choices under the agreed deterministic ordering.

Example: leader weights `5, 3, 2` become `0.5, 0.3, 0.2`. With no supplied weights, three soft questions receive `1/3` each. Record `weight_source` as `leader` or `equal_default` and version the policy.

If one open answer yields several preferences under the same question, retain that question's total weight. Agree how its subcriteria are combined; an equal average is a reasonable initial rule. Repeating a preference or writing a longer answer must not multiply its weight. Overlapping questions need a reviewed mapping to avoid counting the same criterion twice unintentionally.

Do not infer importance solely from answer length, strong wording, or variation across members. Alternative automatic weight policies can be added as explicit experiments once the baseline works.

### Stage E: generate candidates and return the contract

Enumerate activity start times on the agreed 30-minute grid, retaining starts whose entire duration fits an allowed activity window. Deduplicate candidates from overlapping windows and assign stable IDs. Keep concrete timestamps alongside any grid indexes.

Pass all valid candidates to the matcher. Your teammate checks member availability, budgets, requirements, and unknown facts. Your code does not remove candidates just because you predict they will rank poorly.

## 6. How your output affects the final result

Your teammate first checks hard constraints. Only fully feasible candidates proceed to authoritative ranking.

For a proposed weighted-scoring baseline, your teammate computes a utility between 0 and 1 for each member, candidate, and soft question:

```text
member_score(member, candidate)
    = sum(question_weight × question_utility(member, candidate))
```

For example, `categorical_match_v1` could return 1 for a matching preference and 0 for a conflicting value; unknown activity facts remain unresolved. Explicit indifference should have a documented constant utility, rather than being treated as missing.

The team must also choose how member scores become a group ranking. One proposal that extends the original policy is highest minimum member score, then highest mean member score, then cost/time/stable ID. This is a proposal to agree together: the original documents rank raw activity ratings and do not yet specify weighted custom questions.

Your responsibility is to provide consistent extracted values, question mappings, and weights. Your teammate owns calculating utilities, group scores, and the final order.

## 7. Algorithms and methods relevant to your part

| Method | Use in your work | Limitation |
| --- | --- | --- |
| Direct mappings and validation rules | Structured selections, ratings, units, bounds | Only covers declared fields |
| Pattern matching and parsing | Clear amounts, dates, and explicit phrases | Brittle with ambiguity and varied phrasing |
| Schema-constrained LLM extraction | Map open answers to supported typed criteria | Must be checked against examples and validated; can misinterpret text |
| Equal or leader-specified weight normalization | Transparent initial weight policy | Defaults express a chosen policy, not discovered user priorities |

You do not need to train a model to start. Keep one extractor interface so you can compare a rules baseline with an LLM extractor using the same examples. Ask your teammate to keep matching deterministic for a given processed input.

## 8. Suggested files

```text
services/decision/
  preprocessing/
    schemas.py
    question_mapping.py
    extractors.py
    normalization.py
    weights.py
    candidates.py
    pipeline.py
  tests/preprocessing/
  fixtures/preprocessing/
    mock_options.json
    mock_responses.json
    expected_evaluation_input.json
```

These names assume Python, as suggested in the existing plan. The same separation works in TypeScript if that is the team's chosen stack.

## 9. Work plan and checkpoints

| When | Your work | Completion check |
| --- | --- | --- |
| First session | Agree `EvaluationInputV1`, criterion meanings, ownership, and weight/scoring policies with teammate | Teammate can describe exactly how each output field will be used |
| Days 1–2 | Create mock inputs, manually written expected outputs, and schemas | Both of you can load and validate the same fixture |
| Week 1 | Structured mapping, normalization, candidate generation, and default/leader weights | Mock structured input produces the expected object |
| Week 2 | Open-answer extraction for supported criteria and first matcher integration | Mixed structured/open answers produce an explained result end to end |
| Week 3 | Ambiguous answers, contradictions, unknown facts, and clarification handling | Unresolved input cannot produce an authoritative winner |
| Week 4 | Replace mock loading with immutable snapshot adapters; cover revisions and retries | Same interface works with real services; stale inputs fail clearly |
| Week 5 | Compare extraction methods and measure the entire processing pipeline | Report extraction errors, latency, failure rate, and model cost if applicable |
| Week 6 | Fix remaining failures, document the contract, and prepare demo fixtures | Teammate can run the pipeline from documented commands |

Integrate against fixtures immediately. Service adapters should be added earlier if the other teams' APIs are available; do not wait until week four to discover a contract mismatch.

For model-based extraction, save and reuse the accepted normalized artifact for each immutable input and processing-policy version. Repeated matching requests should not re-extract the same text and produce different authoritative interpretations. Include processing versions/artifact identity as well as algorithm version in result identity when the existing snapshot/version key is extended.

## 10. How to check your work

Create a small, manually labelled dataset of roughly 30–50 question/answer examples. Include straightforward answers, negation, multiple preferences, vague dates, conflicting amounts, explicit unlimited budget, and unsupported criteria. Reserve some examples for evaluation rather than tuning rules/prompts against every example.

Measure extraction accuracy by field, including criterion, value, units, and hard-versus-soft classification. Track cases that should request clarification separately. Validate schema correctness too, but do not count valid JSON as proof of correct meaning.

Your pipeline checks should cover:

- Equivalent structured and open answers produce equivalent normalized meanings.
- Missing members, stale responses, and mismatched snapshot IDs are detected.
- Unknown and contradictory answers remain visible.
- Soft weights sum to 1 when soft questions exist; hard constraints have no score weight.
- Repeated text does not increase a question's influence.
- Time candidates fit activity windows, including duration and boundary cases.
- An extracted hard constraint actually changes feasibility when passed to the matcher.
- Shared recommendation output excludes raw answers and private individual values.

Start with the smallest useful demonstration: two activities, two members, one structured budget question, one open preference question, and one leader/default weight configuration. Produce the expected JSON by hand first, then make your code reproduce it.

## References

- [Existing architecture and service contracts](../../../what2do-architecture.md)
- [Existing project plan and decision policy](../../what2do-project-plan.md)
- Updated scope supplied in this conversation: structured and open questions, semantic extraction, optional leader question weights, and calculated defaults.
