# Weighting policy v1

This document freezes the legacy generic-option weighting behaviour. It
describes the behaviour implemented by sparse preprocessing,
`generic_to_option_v1`, and the generic matcher; it does not propose new
weighting rules.

The normal frontend publishing flow now writes `weighting_policy_version:
"v2"` for newly created sessions. `v1` remains supported exclusively for
snapshots created before that change, explicit compatibility/replay, and
controlled comparisons. A snapshot that omits the version is still interpreted
as v1 to preserve historical results.

## Scope and authority

`v1` applies to soft preferences in `execution_mode: options` sessions.
Hard constraints are feasibility checks and never receive scoring weight.
Informational, unclassified, and importance questions also receive no direct
scoring weight.

Weighting has two separate concerns:

1. **Shared question relevance** is set by the organiser's question settings
   or by a resolved question interpretation. It describes how much a question
   contributes to the group's common scoring baseline.
2. **Member importance** adjusts that baseline separately for each member. It
   describes how much an active criterion matters to that member.

The algorithm does not infer a group's social priorities from popularity,
previous results, or a model response. The group objective aggregates the
resulting per-member scores, but does not change their weights.

## Input sources

### Organiser question levels

The current frontend serialises the organiser's soft-question choice as
`relevance`:

| Organiser level | Relevance value |
| --- | ---: |
| Less | 0.25 |
| Normal | 0.50 |
| More | 1.00 |

Consequently, absent duplicate-criterion sharing, the intended ratio is
`1 : 2 : 4`. `weight_level` is retained as metadata for the UI; the numeric
`relevance` value is the value consumed by preprocessing.

An integration client may alternatively provide a non-negative
`leader_weight`. When present, it is used as the raw question value after
scaling all supplied leader weights by their maximum (or `1`, whichever is
larger). The current frontend does not send `leader_weight`.

### Question interpretation

For a leader-declared question, the supplied role, criterion, and relevance
are used. For an unresolved question, local rules or an optional semantic
provider may classify it. A model-provided `semantic_relevance` can therefore
be used as a question's fallback raw value. The model does not set member
importance or the group objective.

### Member importance

Members can provide:

- explicit non-negative criterion multipliers, such as `{ "quiet": 2 }`;
- grounded ordinal comparisons, such as `quiet matters more than cost`; or
- per-question importance data collected by Participation.

Ordinal comparisons become longest-path tiers: the lowest tier is `1`, and
each declared step above it adds `1`. They express ordering, not a ratio claimed
by the member. Contradictions, cycles, inactive criteria, and all-zero active
importance block scoring with a clarification issue.

## Calculation

### 1. Resolve shared question weights

Only soft questions participate. Let `r(q)` be the raw value for question `q`:

```text
r(q) = leader_weight(q) / leader_scale,    when leader_weight is supplied
     = relevance(q) / duplicate_count(c),  otherwise
```

Where `c` is the question's criterion and `duplicate_count(c)` is the number
of automatically weighted soft questions on that criterion. The supplied
leader-weight path does not use this duplicate divisor.

Question weight is then normalised across all soft questions:

```text
question_weight(q) = r(q) / sum(r(active soft questions))
```

If every raw value is zero in the legacy activity/time path, that path falls
back to equal weights. In the generic sparse path, zero total relevance instead
produces `NO_RELEVANT_SOFT_QUESTION`, so scoring cannot proceed silently.

### 2. Split question weight across one member's active criteria

A single answer can produce more than one distinct soft criterion. For a member
`m`, a question's mass is split equally across those criteria:

```text
base_weight(m, q, c) = question_weight(q) / active_criteria_from_answer(m, q)
```

Explicit indifference does not contribute active scoring mass. If a member is
indifferent on every soft criterion, the generic matcher assigns that member a
neutral candidate score of `0.5`.

### 3. Apply member importance and normalise per member

Let `i(m, c)` be the member's explicit multiplier, ordinal tier, or default
value `1`:

```text
raw_member_weight(m, q, c) = base_weight(m, q, c) * i(m, c)

effective_weight(m, q, c) = raw_member_weight(m, q, c)
                             / sum(raw_member_weight for member m)
```

For every member with resolved active preferences, effective weights sum to
one. This ensures that a member with more answered questions does not receive
more total influence than another required member.

## Use by the matcher

For each feasible candidate and required member, the generic matcher evaluates
the declared utility for every active `(question, criterion)` row. Utilities are
bounded to `0..1`. The member score is the weighted mean using that member's
`effective_weight` rows; if some rows are explicitly indifferent, the matcher
renormalises over the remaining active rows.

The group objective then combines member scores. `maximin_then_average` and
`weighted_fairness` use the same member scores and weights; they differ only in
group aggregation and ranking.

## Provenance exported in the handoff

The prepared handoff retains enough information to audit the result:

- `scoring_model.questions[]`: question weight, source, relevance, role, and
  utility rule;
- `scoring_model.member_weights[]`: base weight, importance multiplier/source,
  effective weight, resolution status, and a `weight_explanation` containing
  the question mass, criterion split count, raw weight, and per-member
  normalisation total;
- `importance[]`: the member declarations and their evidence/provenance;
- `scoring_model.group_objective`: the frozen fairness mode and parameters.

## Known limitations of v1

- The `Less / Normal / More` ratio is fixed at `1 : 2 : 4`.
- `leader_weight` can bypass automatic duplicate-criterion sharing.
- Explicit numeric member multipliers have a very large accepted range before
  per-member normalisation, so an extreme value can make one criterion dominate
  that member's score.
- Question relevance and decision importance are distinct concepts but are both
  represented in the final effective weights, which can be difficult to explain
  in the current UI.
- Model relevance can supply a fallback raw question value. It should be treated
  as interpreted configuration, not as an independent statement of group value.

These are deliberate targets for a future, versioned `v2` policy. Existing
completed runs must continue to use their frozen v1 handoff values.

## Verification invariants

The v1 tests verify that:

- hard constraints receive no scoring weight;
- shared soft question weights are normalised;
- each required member's resolved effective weights sum to one;
- duplicate automatic criteria share their raw relevance;
- member importance changes only that member's balance;
- conflicting/cyclic importance declarations are not scored; and
- fairness modes aggregate the same per-member scores.
