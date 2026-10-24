# Algorithm design journey

This document records why the Decision Service ranks options the way it does,
which choices are policy decisions, and which alternatives remain deliberately
out of scope. It complements the executable input contract in
[algorithm-input-shape.md](algorithm-input-shape.md) and the client-facing
result contract in [RESULT_PRESENTATION.md](RESULT_PRESENTATION.md).

## Problem framing

What2Do extends the overlap-finding idea of When2meet. A feasible time is not
by itself a good group decision: members can have must-haves, preferences with
different importance, incomplete information, and legitimate disagreement.

The algorithm therefore needs to answer three separate questions in order:

1. Can this option be considered for the required group?
2. How suitable is it for each required member?
3. Which feasible option best follows the round's declared group policy?

Keeping those questions separate avoids treating a hard requirement as merely
a low score, or allowing an opaque group score to hide an unresolved fact.

## Pipeline boundary

The pipeline has distinct ownership:

```text
Participation answers -> preprocessing -> execution adapter -> matcher -> recommendation view
```

- Participation owns submitted member answers and private constraints.
- Preprocessing turns structured answers or supported interpretations into
  typed criteria, confirmed hard constraints, normalized soft preferences, and
  per-member effective weights.
- An execution adapter selects a supported matcher and rejects a preparation it
  cannot execute safely. `generic_to_option_v1` is the default generic-option
  path; scheduled and scenario paths use their respective adapters.
- The matcher evaluates only the fixed handoff contract. It does not infer
  meaning from free text or query external sources.
- `recommendation_view` turns aggregate matcher output into a shared,
  privacy-safe client contract.

This boundary is intentional. Ambiguity and missing context are a processing
problem. Requiring the matcher to interpret them would make outcomes difficult
to reproduce and test.

## Chosen decision procedure

For every candidate, the generic matcher performs the following sequence.

1. Validate the handoff: IDs, types, units, supported utility rules, references,
   normalized member weights, objective, and ranking policy.
2. Apply hard feasibility checks for all required members. A confirmed failed
   requirement makes the candidate infeasible. Missing evidence for a hard
   requirement makes it unresolved.
3. Apply explicit member option flags. `cannot_join` is infeasible;
   `needs_information` is unresolved.
4. Score every feasible candidate per required member using the normalized
   member weights and declared utility rules. Utilities are bounded to `0..1`.
5. Block the decision when a candidate remains unresolved. A partially scored
   candidate might otherwise be incorrectly recommended over a candidate whose
   missing evidence would make it better.
6. Aggregate the member scores with the frozen group objective.
7. Apply deterministic ranking tie-breakers and return Pareto alternatives.

Hard constraints are never compensated for by popularity. Soft preferences are
not silently converted into hard constraints.

## Scoring model

Preprocessing assigns each member's active soft criteria effective weights that
sum to one. For a candidate, the member score is the weighted sum of that
member's declared utility values. This normalizes importance *within* each
member without allowing one member with more answered questions to contribute
more total mass than another.

Supported generic utilities include categorical match/avoidance, explicit
indifference, numeric target/direction/range utilities, and tag overlap.
Categorical and tag-overlap utilities also apply normalized content-token and
phrase-subset similarity (`_phrase_similarity`) when exact strings differ so
that descriptive sourced claims (for example, `"singapore style artisanal craft
cocktails"` or `"cosy contemporary"`) align with concise member preferences
(`"craft cocktails"` or `"cozy"`). When a member answers `"No preference"`
(`indifferent`) on a subset of criteria while expressing active preferences on
others, their member score is re-normalized over their active criteria so that
being flexible on secondary questions does not artificially cap their score at
`50%`. When a member is indifferent across all soft criteria, their score
remains `0.5`.
Their input types and validation rules are defined by the execution contract.

The group objective receives the same per-member scores regardless of mode.
Changing mode changes aggregation and ranking policy, not the underlying
member scoring.

## Fairness policies

### Maximin then average

This is the contract baseline policy. It orders candidates by the lowest required-member
score first, then average score. It answers: "Which choice avoids leaving any
required person with the worst fit?"

It is appropriate when inclusion and avoiding a strongly disadvantaged member
matter more than maximising collective preference.

### Weighted fairness

This policy combines minimum satisfaction, average satisfaction, and a penalty
for disagreement between member scores:

```text
group_score = (minimum_weight * minimum + average_weight * average)
              / (minimum_weight + average_weight)
              - fairness_weight * population_variance(member_scores)
```

It is appropriate when the group wants to balance overall fit and fairness
without letting a tiny difference in minimum score override strong group
consensus. For `facts-v1` option rounds without an explicit custom objective,
`decision_service/service/execution.py` applies `BLENDED_FAIRNESS_OBJECTIVE`
(`minimum_score_weight: 0.5`, `average_score_weight: 0.5`,
`fairness_weight: 0.15`). If an objective is absent on raw contract inputs, the
fallback remains `maximin_then_average`.

The algorithm does not select a policy automatically from member answers.
That would make an important social choice implicit and difficult to explain.

### Adversarial example

The fairness tests use two candidates with the same member scores under both
policies:

| Candidate | Member scores | Minimum | Average |
| --- | --- | --- | --- |
| Balanced | `(0.6, 0.6)` | `0.6` | `0.6` |
| Popular but uneven | `(0.4, 1.0)` | `0.4` | `0.7` |

Maximin selects **Balanced**. An average-heavy weighted policy selects
**Popular but uneven**. Adding a sufficiently strong variance penalty selects
**Balanced** again. These tests demonstrate that both modes reuse identical
member scoring and differ only because of the declared group objective.

## Ranking and ties

`rank` is a deterministic display order. After the objective metrics, the
generic matcher uses optional lower `estimated_cost_minor`, optional earlier
`start_at`, then stable option ID. Missing cost or time metadata sorts after
supplied metadata, and the ID fallback ensures repeatable results.

Tie-breakers are useful for display and reproducibility, but they should not
pretend to be a meaningful group preference. The output therefore also has:

- `primary_rank`: dense rank before cost, time, or ID tie-breakers.
- `primary_objective_tie_size`: number of candidates tied at that primary rank.

A tie size above one means the candidates are equally suitable under the group
objective. The client may still list one first, but should communicate the tie
rather than claim a substantive winner.

## Pareto alternatives

Pareto analysis does not choose the recommendation. The group objective chooses
the winner. The generic matcher retains candidates not dominated on both minimum
and average member satisfaction, and the presentation layer exposes them as
"Other strong trade-offs."

This is useful when an alternative has stronger average satisfaction but a
weaker worst-off-member result, or the reverse. It is intentionally not a
separate voting rule and does not override hard constraints or the organiser's
chosen objective.

## Alternatives considered

| Alternative | Decision | Reason |
| --- | --- | --- |
| Plain greedy total-score choice | Not sufficient on its own | It can recommend an option that is very poor for one required member. |
| Maximin then average | Implemented as the default | Clear fairness baseline and easy explanation. |
| Weighted fairness | Implemented as configurable policy | Makes explicit trade-offs between minimum fit, average fit, and disagreement. |
| Pareto frontier | Implemented as explanation | Shows strong trade-offs without replacing the declared policy. |
| Voting methods | Deferred | Need product choices about ballots, strategic behaviour, and how votes interact with hard constraints. |
| Nash social welfare | Deferred | Could be valuable, but zero/near-zero utilities and interpretation need an agreed product policy. |
| Integer/constraint optimisation | Deferred | Useful for allocations, capacities, or combinations of options, but current rounds choose one candidate. |
| Automatic policy selection | Rejected for now | Fairness is a group/organiser governance choice, not an inference problem. |
| More Pareto dimensions | Deferred | Cost, time, confidence, and variance require consistently comparable data and agreed dominance semantics. |

## Verification strategy

Tests are layered so a failure can be localized.

- Contract and adapter tests reject malformed handoffs, unresolved member
  weights, invalid policies, unsupported utilities, and invalid tie metadata.
- Generic matcher tests cover hard constraints, missing soft facts, numeric and
  tag utilities, indifference, ranking tie-breakers, primary-objective ties,
  and the adversarial fairness scenarios.
- Presentation fixtures cover ranked, Pareto, blocked, unresolved, no-feasible,
  pending, setup-review, and failed result states without exposing private
  member data.
- The HTTP lifecycle test confirms an organiser and an authorised participant
  receive the same shared `recommendation_view` while private clarifications
  remain member-specific.

The focused generic-option suite can be run with:

```sh
python -m unittest decision_service.tests.test_generic_option_v1 -v
```

The full cross-service lifecycle test requires the integration Compose stack:

```sh
python -m unittest integration.test_http_lifecycle.ServiceJourneyTests.test_publish_submit_freeze_rank_confirm_and_reopen -v
```

## Current limits and next questions

The current design is intentionally conservative. Unresolved candidates block
the result instead of allowing a recommendation over incomplete evidence. This
protects decision quality but may create more follow-up work for organisers.

Potential future work should be driven by observed product needs:

- organiser-only, privacy-safe guidance about facts that would unblock a result;
- explicit policy selection in the organiser workflow;
- sensitivity analysis that shows whether small policy changes alter the winner;
- richer candidate metadata and comparable cost/time semantics for every
  execution adapter;
- optimisation for capacity, allocation, or multi-option group plans.

Any such change should add a policy version, fixtures that show the intended
trade-off, and an explanation that distinguishes group-level reasoning from
private member answers.
