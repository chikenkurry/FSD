# Recommendation result presentation

`recommendation-view-v1` is the shared, presentation-oriented projection of a
Decision run. It is returned as `recommendation_view` by the public Decision
result and is intended for both organisers and participants in the initial
product experience.

It is deliberately separate from `result`, which remains the raw algorithm
output for API compatibility and diagnostics. A client should render the view
and should not recreate group-decision logic from raw scores.

## Endpoint and audience

Planning exposes the shared result through:

```text
GET /v1/rounds/{round_id}/recommendation
```

During the baseline, every authorised member of the round receives the same
`recommendation_view`. The organiser does not yet receive a separate
decision-improvement view. A future organiser-only extension may describe
additional facts or response changes that could unblock a decision; it must not
reveal another member's private answer or constraint.

## Contract

```json
{
  "schema_version": "recommendation-view-v1",
  "status": "ranked",
  "recommendation": {
    "candidate_id": "option-a",
    "title": "Option A",
    "rank": 1,
    "primary_rank": 1,
    "primary_objective_tie_size": 1,
    "group_score": 0.74,
    "minimum_member_score": 0.62,
    "average_member_score": 0.78,
    "fairness_penalty": 0.01,
    "is_recommended": true
  },
  "alternatives": [],
  "pareto_alternatives": [],
  "unavailable_candidates": [],
  "next_action": null
}
```

| Field | Meaning |
| --- | --- |
| `status` | Decision status: `ranked`, `blocked`, `no_feasible_candidate`, or another execution status. |
| `recommendation` | The first ranked candidate, or `null` when no authoritative recommendation is available. |
| `alternatives` | Remaining ranked candidates in rank order. |
| `rank` | Deterministic display order after policy tie-breakers. |
| `primary_rank` | Dense rank using only the substantive group objective, before cost, time, or ID tie-breakers. |
| `primary_objective_tie_size` | Number of candidates tied at this primary rank. A value above one means there is no substantive winner between those candidates. |
| `pareto_alternatives` | Ranked alternatives on the Pareto frontier, excluding the recommendation. |
| `unavailable_candidates` | Candidates that cannot currently be recommended, with a non-private feasibility state only. |
| `next_action` | A broad action state for the shared UI, or `null` when none is required. |

Candidate IDs are stable execution identifiers. `title` is sourced from the
frozen candidate when present and otherwise falls back to a safe identifier.
For scenario candidates, the frontend may use the candidate ID until a later
presentation enhancement adds scenario date/duration fields explicitly.

`minimum_member_score` and `average_member_score` are normalized values in the
inclusive range `0` to `1`. `group_score` is the declared policy objective and
may be lower when a weighted-fairness policy applies its penalty. Clients should
round only for display and retain the server ordering. When
`primary_objective_tie_size` is above one, clients should present the tied
candidates as equally suitable and use `rank` only for a stable display order.
A higher `group_score`, `minimum_member_score`, or `average_member_score` is
better. A lower `fairness_penalty` represents less variation among member scores.

## Pareto alternatives

Pareto analysis does not select the winner. The declared group objective and
ranking policy select `recommendation`; the frontier supplies meaningful
alternatives when no option is strictly better on every displayed objective.

For the generic matcher, frontier membership is currently evaluated on minimum
and average member satisfaction. `pareto_alternatives` reports structured
comparison labels against the recommendation:

| Code | Suggested shared wording |
| --- | --- |
| `HIGHER_MINIMUM_SATISFACTION` | Better fit for the least-satisfied member. |
| `LOWER_MINIMUM_SATISFACTION` | Lower fit for the least-satisfied member. |
| `HIGHER_AVERAGE_SATISFACTION` | Higher overall group fit. |
| `LOWER_AVERAGE_SATISFACTION` | Lower overall group fit. |
| `EQUIVALENT_GROUP_METRICS` | Similar group-fit metrics. |

The UI should label this section "Other strong trade-offs", rather than expose
the technical term "Pareto frontier". Do not claim an alternative is better
overall when its labels show a trade-off.

## Shared states and actions

| Status / condition | View behavior | `next_action` |
| --- | --- | --- |
| `ranked` | Show recommendation, ranked alternatives, and Pareto trade-offs. | `null` |
| Blocked with fact requests | Do not show a recommendation. Show that more option information is needed. | `OPTION_FACTS_REQUIRED` |
| Other `blocked` result | Do not show a recommendation. Ask members to complete or confirm required information. | `RESPONSES_OR_CONFIRMATIONS_REQUIRED` |
| `no_feasible_candidate` | Do not show a recommendation. Explain that the group should revise options or requirements. | `REVISE_OPTIONS_OR_REQUIREMENTS` |
| `pending` | Show a non-final loading state. Do not infer a recommendation from incomplete data. | `RECOMMENDATION_IN_PROGRESS` |
| `needs_information`, `needs_clarification`, `unsupported`, or `invalid_input` | Do not show a recommendation. Ask the organiser to review the round setup. | `DECISION_SETUP_REVIEW_REQUIRED` |
| `failed` | Show a recoverable error state. Do not expose internal failure details. | `RECOMMENDATION_RETRY_REQUIRED` |

`unavailable_candidates[].status` is intentionally limited to aggregate states
such as `infeasible` or `unresolved`. The view does not expose raw explanation
codes, because a code such as `CANNOT_JOIN` could reveal a member's private
availability or participation preference.

The existing top-level `fact_requests`, `scenario_requests`, and `issues` remain
available to authorised API consumers. They are not replacements for the shared
view and should not be rendered as personal-member explanations.

## Privacy boundary

The shared result must not include:

- Individual member scores or ranking contributions.
- Raw answers, budgets, constraints, evidence, or semantic interpretations.
- A participant ID associated with a feasibility outcome.
- Member-specific flag or explanation codes.

Private review remains available through the clarification endpoint. It is the
only surface that may show a member their own interpreted preferences,
constraints, importance records, and answer-review issues.

## Versioning and verification

New fields may be added to the view. Existing field meanings and the
privacy boundary require a new schema version if changed incompatibly.

Presentation fixtures live in
`decision_service/fixtures/presentation/recommendation_view_cases.json`. They
cover ranked results with and without a Pareto trade-off, blocked results awaiting
option facts or responses, no-feasible-candidate, pending, setup-review, and
failed states. The corresponding regression test is in
`decision_service/tests/test_service_integration.py`.
