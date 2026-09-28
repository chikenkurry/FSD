# Algorithm Input Shape

## Sparse option handoff (`sparse-v2`)

`preprocess(planning_snapshot, response_snapshot)` selects this version when
planning has `options` instead of `activities`. The planning input needs the
immutable round/snapshot IDs, decision question, roster, option names or
`{option_id, title, description?, facts?}` objects, and leader-written
questions. Member answers arrive in the response snapshot. See
`fixtures/preprocessing/planning_grad_trip.json` and `response_grad_trip.json`.

The returned `algorithm_input` has:

```ts
type SparseHandoff = {
  context: { schema_version: "sparse-v2"; round_id: string;
    option_snapshot_id: string; response_snapshot_id: string;
    decision_question: string; currency: string | null;
    cost_scope: string | null; details: object;
    semantic_artifact_id: string | null };
  candidates: { candidate_id: string; option_id: string; title: string;
    description: string; facts: SourcedFact[]; missing_criteria: string[];
    tag_suggestions: { criterion: string; value: string; reason: string;
      status: "hypothesis" }[] }[];
  scenario_requests: { option_id: string; duration_days: number;
    earliest_start_date: string; latest_start_date: string;
    cost_evidence_status: "unknown" | "estimated" | "confirmed";
    cost_evidence?: object }[];
  participants: { participant_id: string; response_status: string }[];
  constraints: object[];
  preferences: object[];
  informational_answers: object[];
  unclassified_answers: object[];
  scoring_model: { questions: object[]; missing_fact_policy: "unresolved" };
};

type SourcedFact = { criterion: string; value: string | number | boolean | (string | number | boolean)[];
  status: "confirmed" | "estimated"; source: string;
  unit?: string; context?: object };
```

The question entries carry `role` (`hard`, `soft`, `informational`, or unresolved
`unclassified`),
`criterion`, `relevance`, `reason`, `inference_source`, and `weight`.
Automatically weighted duplicate topics share their relevance. Hard and
informational questions have `weight: null`. A zero-relevance informational
question is never given equal fallback weight. Each extracted open preference
has an exact answer `evidence` substring. A potential must-have has
`status: needs_confirmation` and triggers clarification.

Option names generate identities and requests for missing criteria; they
generate no factual claims. Sourced option facts can cover any criterion.
Model-generated tags remain hypotheses and cannot satisfy a missing criterion
or hard requirement. Natural-language date extraction requires an evidence
substring and an explicit year in the member answer.
When the questions include both availability and duration, `scenario_requests`
intersect member date intervals, then describe feasible start-date ranges
for the offered durations. A later
evidence collector can attach `planning.scenario_costs` records matching the
option, duration, and date range, with amount, currency, explicit budget scope,
status, and source. When there are no date/duration scenarios, a budget can
instead compare a confirmed option fact under `max_cost`. Estimated costs
keep the result provisional. The current
activity/time matcher must not consume this version.

`status: provisional` retains a partial handoff with issues about unknown
option/scenario facts or missing semantic extraction. `needs_clarification`
also retains partial data when a member answer needs work. Neither is a
confirmed recommendation. The older activity/time contract below is
unchanged and still returns `algorithm_input: null` unless `ready`.

This document describes the expected input shape for the Decision service algorithm. It is a draft contract for the algorithm layer and can be refined as the Planning and Participation service contracts become more specific. The preprocessing prototype in `preprocessing/` produces this shape from immutable mock snapshots.

The main design principle is:

> The processing step may handle messy, incomplete, or free-text inputs, but the algorithm should only receive normalized, typed, explicit data.

The algorithm should not infer missing context from raw text, guess user intent, or silently fill gaps. Those responsibilities belong to the processing step before the algorithm runs.

## Pipeline Position

The intended Decision service pipeline is:

1. Receive participation and planning data.
2. Process raw or partially structured data into fixed decision inputs.
3. Run the algorithm against those fixed inputs.
4. Return ranked candidates and explanation codes.

The algorithm step should always receive the same categories of input, even if earlier services collect data in different ways.

The preprocessing function accepts an immutable planning snapshot, an immutable response snapshot, and a processing policy. The planning snapshot contains `round_id`, `option_snapshot_id`, `option_revision`, `timezone`, `currency`, the exact `roster`, `activities` with windows and attributes, and `questions` with optional `leader_weight`. Provide `decision_question` for model-based relevance assessment; otherwise the provider falls back to the plan description, title, or a generic group-choice goal. The response snapshot contains `round_id`, `option_revision`, `response_snapshot_id`, and `participants`, each with `response_status` and answers linked by `question_id`. See the two JSON fixtures in `fixtures/preprocessing/` for the complete current adapter shape. Planning and Participation still need to confirm the network contracts that provide these fields.

Preprocessing returns `{status, issues, algorithm_input, semantic_evidence?}`. `status` is `ready`, `needs_clarification`, `invalid_input`, or `upstream_unavailable`. Only `ready` contains an algorithm input. Incomplete answers and ambiguous text cause `needs_clarification`; malformed or mismatched snapshots cause `invalid_input`; a model service failure is retryable. Other statuses must not be passed to the matcher. A ready run with model-assessed questions also returns validated `semantic_evidence`; persist it and pass it back on retries to avoid another model interpretation.

Questions with a controlled mapping use `availability`, `budget`, `activity_rating`, `candidate_flag`, `open_requirement`, `open_preference`, or `open_budget`. A question outside that vocabulary uses `semantic_preference` or `semantic_requirement` and a configured semantic provider. It may have `answer_format: "text"`, or `answer_format: "choice"` with `choices: [{choice_id, label}]`. Both formats become an interpreted answer. Model-assisted answer interpretations require an exact evidence substring from the member's answer.

## Algorithm Responsibilities

The algorithm should:

- compare normalized constraints, preferences, and semantic interpretations with each candidate;
- apply hard question results before soft scoring;
- rank feasible candidates using a deterministic policy;
- preserve reason codes for infeasible or unresolved candidates;
- return enough metadata for the product to explain the result.

The algorithm should not:

- interpret free text;
- decide whether a missing value should count as neutral;
- silently relax budget, availability, or hard requirements;
- drop participants from the roster to produce a winner;
- expose private response values in shared explanations.

## Top-Level Input

```ts
type DecisionAlgorithmInput = {
  context: DecisionContext;
  candidates: Candidate[];
  participants: Participant[];
  constraints: ParticipantConstraint[];
  preferences: ParticipantPreference[];
  semantic_interpretations: SemanticInterpretation[];
  scoring_model: ScoringModel;
};
```

## Context

The context identifies the immutable planning round and input snapshots used for the run.

```ts
type DecisionContext = {
  round_id: string;
  option_snapshot_id: string;
  response_snapshot_id: string;
  timezone: string;
  algorithm_version: string;
  policy_version: string;
  processing_version: string;
  semantic_model: string | null;
  semantic_artifact_id: string | null;
};
```

Notes:

- `timezone` should be an IANA time zone, such as `Asia/Singapore`.
- `algorithm_version` and `policy_version` make previous recommendations explainable after future changes.
- The algorithm should evaluate immutable snapshots, not live mutable response data.

## Candidate Outcomes

A candidate is one complete possible outcome that can be evaluated and ranked.

For What2Do, a candidate should usually be an activity plus a concrete time range, not just an activity.

```ts
type Candidate = {
  candidate_id: string;
  activity_id: string;
  option_revision: string;
  title: string;
  description: string;
  start_at: string;
  end_at: string;
  duration_minutes: number;
  estimated_cost_minor: number | null;
  currency: string;
  attributes: CandidateAttribute[];
};

type CandidateAttribute = {
  attribute_id: string;
  value: "yes" | "no" | "unknown";
};
```

Notes:

- `estimated_cost_minor` uses minor currency units, for example cents.
- `null` cost means missing or unevaluated, not free.
- A free option should use `0`.
- `start_at` and `end_at` should be timestamp instants that can be interpreted with the round time zone.

## Participants

The participant list defines whose inputs count for the decision.

```ts
type Participant = {
  participant_id: string;
  display_label?: string;
  response_status: "complete" | "incomplete" | "stale" | "needs_clarification";
  is_required_for_decision: boolean;
};
```

Notes:

- For the MVP, every approved roster member should usually be required.
- Final recommendation should be blocked when required participants have incomplete or stale responses.
- `display_label` is optional and should not be required for algorithm correctness.

## Hard Constraints

Hard constraints determine whether a candidate can be considered feasible.

```ts
type ParticipantConstraint = {
  participant_id: string;
  availability: AvailabilityConstraint;
  budget: BudgetConstraint;
  required_attributes: RequiredAttributeConstraint[];
  candidate_flags: CandidateFlag[];
};

type AvailabilityConstraint = {
  available_intervals: TimeInterval[];
};

type TimeInterval = {
  start_at: string;
  end_at: string;
};

type BudgetConstraint = {
  kind: "limited" | "unlimited" | "missing";
  max_cost_minor?: number;
  currency?: string;
};

type RequiredAttributeConstraint = {
  attribute_id: string;
  required_value: "yes" | "no";
  source_question_id: string;
};

type CandidateFlag = {
  candidate_id: string;
  flag: "cannot_join" | "needs_information";
  source_question_id: string;
};
```

Constraint rules:

- A participant must be available for the full candidate duration.
- A limited budget passes only when `candidate.estimated_cost_minor <= max_cost_minor`.
- An unlimited budget passes the budget check.
- A missing budget is incomplete and should not be treated as zero or unlimited.
- Required attributes pass only when the candidate attribute is known and satisfies the requirement.
- `unknown` does not satisfy a required attribute.
- `cannot_join` makes the candidate infeasible for that participant.
- `needs_information` makes the candidate unresolved and not confirmable.

## Soft Preferences

Soft preferences influence ranking only after hard constraints are satisfied.

```ts
type ParticipantPreference = {
  participant_id: string;
  kind: "rating" | "attribute_preference" | "indifferent";
  candidate_id?: string;
  activity_id?: string;
  rating?: 0 | 1 | 2 | 3 | 4;
  attribute_id?: string;
  preferred_value?: "yes" | "no";
  utility_rule?: "attribute_match_v1" | "neutral_v1";
  source_question_id: string;
};
```

Suggested rating scale:

| Value | Meaning |
| --- | --- |
| 0 | Strongly dislike |
| 1 | Dislike |
| 2 | Neutral or explicit no preference |
| 3 | Like |
| 4 | Love |

Notes:

- `kind: "rating"` requires an `activity_id` or `candidate_id` and a `rating`.
- `kind: "attribute_preference"` requires `attribute_id`, `preferred_value`, and `utility_rule: "attribute_match_v1"`. The matcher compares it with the candidate's known attribute fact.
- `kind: "indifferent"` is an explicit no-preference answer with `utility_rule: "neutral_v1"`; the matcher must define a fixed neutral utility for it.
- Missing ratings should not automatically become neutral. The processing step may convert an explicit rating answer of "no preference" to `2`.
- Several preferences from one question share that question's weight; aggregate their utilities before applying that weight.

## Interpreted Meaning

`semantic_interpretations` records the model's normalized meaning for generic text or choice questions. The provider sees the question, answer, and decision context, but no candidates during answer extraction. It is private internal data; public result APIs should return only aggregate explanations.

```ts
type SemanticInterpretation = {
  participant_id: string;
  question_id: string;
  kind: "semantic_preference" | "semantic_requirement";
  status: "resolved";
  criterion: string;
  value: string;
  meaning: string;
  evidence: string;
};
```

An unresolved model interpretation causes `needs_clarification`, so only resolved interpretations reach the matcher. `evidence` is an exact substring of the member answer. `criterion` and `value` are model-generated strings, not a shared ontology; the matcher must agree on their meaning or use `meaning` and candidate facts when comparing them. Candidate facts can be unknown or absent, so a missing fact cannot prove a requirement passes.

The matcher owns all member-to-candidate comparisons, hard pass/fail decisions, soft fit scores, aggregation, and ranking. The two developers should agree on how the matcher consumes free-form semantic values and how it handles missing candidate evidence before using results for decisions.

## Scoring Model

The scoring model describes how normalized questions and answers should contribute to candidate scores.

```ts
type ScoringModel = {
  questions: QuestionDefinition[];
  ranking_policy: RankingPolicy;
  missing_value_policy: MissingValuePolicy;
};
```

### Questions

```ts
type QuestionDefinition = {
  question_id: string;
  label: string;
  kind: "availability" | "budget" | "activity_rating" | "candidate_flag" | "open_requirement" | "open_preference" | "open_budget" | "semantic_preference" | "semantic_requirement";
  weight: number | null;
  weight_source: "leader" | "auto_relevance" | "model_relevance" | "no_relevance_fallback" | null;
  relevance: number | null;
  criterion?: string;
  relevance_reason?: string;
  is_hard_constraint: boolean;
  aggregation: "direct" | "average";
};
```

Notes:

- Soft-question weights are normalized across questions before the algorithm runs; hard questions have `weight: null`.
- With a configured semantic provider, every soft question without a leader weight receives a validated model relevance in `[0,1]` based on the plan's decision question, the question, and option facts. Member answers are excluded. Without a provider, deterministic relevance remains available for supported questions: direct activity rating has relevance `1`, and mapped attributes use the fraction of activities with known facts times `(0.25 + 0.75 × distinction)`, averaged across attributes. `distinction` is `1` when known options differ and `0` otherwise. Generic semantic questions require a provider or saved evidence.
- Repeated automatic questions mapped to the same topic share that topic's raw relevance, so duplication does not multiply its influence. Supplied leader weights are scaled by `max(1, largest supplied weight)` before mixing them with calculated relevance for missing weights. The resulting raw values are divided by their sum. This supports fully or partly supplied weights. If every raw weight is zero, the unresolved option evidence cannot determine relative relevance, so soft questions receive equal fallback weights marked `no_relevance_fallback`.
- These automatic weights measure how useful questions are for distinguishing the supplied options. They do not claim to measure how much members personally care.
- `direct` applies to a single activity rating. `average` combines several extracted preferences from one open question without multiplying its importance.
- Availability, budget, and hard requirements are evaluated before soft scoring.

### Ranking Policy

```ts
type RankingPolicy = {
  feasibility_policy: "all_required_participants";
  sort_order: RankingCriterion[];
};

type RankingCriterion =
  | "highest_min_member_score"
  | "highest_average_member_score"
  | "lowest_estimated_cost"
  | "earliest_start"
  | "stable_candidate_id";
```

Proposed ranking order when weighted soft questions are enabled:

1. Highest minimum member score.
2. Highest average member score.
3. Lowest estimated cost.
4. Earliest start.
5. Stable candidate ID.

The matcher may map an activity rating to `rating / 4`, explicit indifference to `0.5`, and a known attribute match to `1` or conflict to `0`. It must calculate its own per-member, per-candidate fit for each soft question and decide how several preferences from one question combine. It then sums `question.weight × fit` for each member and applies the ranking policy. The team should review this proposed policy before using it for authoritative results.

### Missing Value Policy

```ts
type MissingValuePolicy = {
  missing_budget: "incomplete";
  missing_rating: "incomplete";
  missing_required_attribute: "unresolved";
  missing_availability: "unavailable";
  no_preference: "neutral";
};
```

Notes:

- Missing and explicit neutral values must remain distinct.
- The processing step should mark why a value is missing or how it was normalized.
- The algorithm should follow this policy rather than inventing fallback behavior.

## Expected Output Shape

The algorithm should return ranked feasible candidates and explanations for both feasible and infeasible candidates.

```ts
type DecisionAlgorithmOutput = {
  run_id: string;
  algorithm_version: string;
  policy_version: string;
  status: "ranked" | "blocked" | "no_feasible_candidate";
  ranked_candidates: RankedCandidate[];
  candidate_results: CandidateResult[];
};

type RankedCandidate = {
  candidate_id: string;
  rank: number;
  min_member_score: number;
  average_member_score: number;
  estimated_cost_minor: number | null;
  explanation_codes: ExplanationCode[];
};

type CandidateResult = {
  candidate_id: string;
  feasibility: "feasible" | "infeasible" | "unresolved";
  explanation_codes: ExplanationCode[];
};

type ExplanationCode =
  | "INCOMPLETE_RESPONSE"
  | "STALE_RESPONSE"
  | "NO_TIME_OVERLAP"
  | "BUDGET_CONFLICT"
  | "MISSING_COST"
  | "MISSING_OPTION_FACT"
  | "REQUIRED_ATTRIBUTE_NOT_MET"
  | "CANNOT_JOIN"
  | "NEEDS_INFORMATION"
  | "LOWER_MIN_RATING"
  | "LOWER_AVERAGE_RATING"
  | "TIE_BROKEN_BY_COST"
  | "TIE_BROKEN_BY_TIME"
  | "TIE_BROKEN_BY_STABLE_ID";
```

Shared product explanations should use aggregate wording and avoid exposing private values such as individual budget caps or private notes.

## Implementation Notes

- Keep hard constraints separate from soft preference scoring.
- Keep the first implementation straightforward and deterministic.
- Store failed checks as structured reason codes for explanations.
- Use stable tie breakers so repeated runs on the same snapshots return the same order.
- Treat the straightforward implementation as the correctness baseline if optimized versions are added later.
