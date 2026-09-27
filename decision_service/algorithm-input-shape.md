# Algorithm Input Shape

This document describes the expected input shape for the Decision service algorithm. It is a draft contract for the algorithm layer and can be refined as the Planning and Participation service contracts become more specific.

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

## Algorithm Responsibilities

The algorithm should:

- evaluate whether each candidate outcome is feasible;
- apply hard constraints before soft scoring;
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
  required_value: "yes";
};

type CandidateFlag = {
  candidate_id: string;
  flag: "cannot_join" | "needs_information";
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
  candidate_id?: string;
  activity_id?: string;
  rating: 0 | 1 | 2 | 3 | 4;
  source_question_id?: string;
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

- Missing ratings should not automatically become neutral.
- The processing step may convert an explicit "no preference" answer to `2`.
- Preferences may apply to an activity or to a specific candidate, depending on the final contract.

## Scoring Model

The scoring model describes how normalized questions and answers should contribute to candidate scores.

```ts
type ScoringModel = {
  questions: QuestionDefinition[];
  option_weights: OptionWeight[];
  ranking_policy: RankingPolicy;
  missing_value_policy: MissingValuePolicy;
};
```

### Questions

```ts
type QuestionDefinition = {
  question_id: string;
  label: string;
  weight_by_candidate: Record<string, number>;
  is_hard_constraint: boolean;
  aggregation: "sum" | "average" | "minimum" | "maximum" | "veto";
};
```

Notes:

- Question weights should be explicit and normalized before the algorithm runs.
- If a question represents a hard constraint, it should be evaluated before soft scoring.
- For the MVP, many core constraints may be represented directly rather than through generic weighted questions.

### Option Weights

```ts
type OptionWeight = {
  question_id: string;
  option_id: string;
  weight_by_candidate: Record<string, number>;
  is_hard_constraint: boolean;
};
```

Notes:

- Option weights are useful for generalized survey-style decision inputs.
- They should not be used to override explicit hard constraints such as availability or budget.

### Ranking Policy

```ts
type RankingPolicy = {
  feasibility_policy: "all_required_participants";
  sort_order: RankingCriterion[];
};

type RankingCriterion =
  | "highest_min_rating"
  | "highest_average_rating"
  | "lowest_estimated_cost"
  | "earliest_start"
  | "stable_candidate_id";
```

Suggested MVP ranking order:

1. Highest minimum member rating.
2. Highest average member rating.
3. Lowest estimated cost.
4. Earliest start.
5. Stable candidate ID.

This policy prioritizes avoiding a strongly disliked option before maximizing average enthusiasm.

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
  min_rating: number;
  average_rating: number;
  average_preference_score: number;
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

