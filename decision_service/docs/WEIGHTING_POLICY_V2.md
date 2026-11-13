# Weighting policy v2

`v2` is the default policy for new generic-option sessions. It keeps the
existing member-importance calculation and algorithm group objectives
unchanged. Its purpose is narrowly scoped: repeated questions about the same
criterion must not obtain extra shared influence simply because the criterion
was split into several prompts.

## Selecting the policy

Add this optional field to a frozen Planning snapshot:

```json
{ "weighting_policy_version": "v2" }
```

The normal frontend publishing flow writes this field for newly created
sessions. Omitting it continues to select `v1`, preserving completed and
historical sessions exactly. The service validates the value as either `v1` or
`v2`, passes it to both execution and preview preprocessing, and freezes the
resulting policy record in the algorithm handoff.

## Shared question calculation

For every soft criterion `c`, first calculate its organiser priority as the
largest relevance among its questions:

```text
criterion_priority(c) = max(relevance(q) for soft questions q about c)
```

If `leader_weight` is supplied for a question, it is first scaled by the
largest supplied leader weight (as in v1) and then participates in that
maximum. Criterion priorities are normalised across distinct soft criteria.
Each criterion's normalised mass is divided equally across its own questions:

```text
criterion_mass(c) = criterion_priority(c) / sum(criterion_priority)
question_weight(q) = criterion_mass(c) / question_count(c)
```

For example, questions with relevance `1.0` and `0.25` about *cuisine*, plus
one question with relevance `0.5` about *vibe*, receive weights `1/3`, `1/3`,
and `1/3`. Cuisine receives two-thirds of the shared mass because its highest
declared priority is twice vibe's; its two prompts share that mass rather than
stacking their relevance.

## What does not change

- Hard constraints remain feasibility checks with no scoring mass.
- A member's active criteria still split a question's mass equally.
- Explicit member multipliers and ordinal importance tiers still adjust only
  that member's weights, then normalise per member.
- `maximin_then_average` and `weighted_fairness` still aggregate the same
  per-member candidate scores; they do not select a weighting policy.

Every `member_weights[].weight_explanation` includes the selected policy
version, allowing a returned result to be audited without guessing which
calculation generated it.

## Verification

`test_v2_allocates_one_criterion_mass_then_splits_repeated_questions` verifies
the duplicate-criterion rule and confirms that `v2` is carried from the
Planning snapshot through preprocessing and into the executable algorithm
input.
