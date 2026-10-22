# Recommendation result presentation

`recommendation-view-v1` is the shared, presentation-oriented projection of a
Decision run. It is returned as `recommendation_view` by the public Decision
result and is intended for both organisers and participants in the initial
product experience.

It is separate from `result`, which retains an allowlisted compatibility shape
containing identifiers, aggregate scores and feasibility states. Raw diagnostics
remain in the private stored artifact. A client should render the view and should
not recreate group-decision logic from raw scores.

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

Candidate IDs are stable execution identifiers. `title` comes from the frozen
candidate or its frozen source option, falling back to an identifier only for
older artifacts without that metadata. Scheduled candidates include
`source_option_id`, `start_at` and `end_at`. Scenario candidates include
`source_option_id` and `scenario` with `duration_days`, `earliest_start_date` and
`latest_start_date`; a date window is never presented as a selected start instant.
When available, `estimated_cost_minor`, `currency` and `currency_minor_digits`
describe the public option cost. A null cost means unknown, not free.

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
In addition, `public_result` includes a top-level `attribute_breakdown` map
keyed by candidate ID. Each entry lists the candidate's evaluated criteria with
aggregate fit score (`0..1`), question weight, confirmed value/tags, aggregate
member alignment counts (`matched_members` / `total_members`), privacy-safe
reasoning text, and sourced citations when supplemented.

## Privacy boundary

The shared result must not include:

- Individual member scores or ranking contributions.
- Raw answers, budgets, constraints, evidence, or semantic interpretations.
- A participant ID associated with a feasibility outcome.
- Member-specific flag or explanation codes.

Private review remains available through the clarification endpoint. It is the
only surface that may show a member their own interpreted preferences,
constraints, importance records, and answer-review issues.

This boundary applies to the **entire HTTP response**, including `result`.
Candidate explanation codes, raw matcher issue messages, arbitrary result
extensions and member-scoped processing issues are omitted from shared results.
`result.issues` is retained as an empty array where present for compatibility.
Consumers previously reading diagnostic codes from public results must use the
member's private review instead. The stored artifact and internal selection
validation retain the full result; presentation never mutates that artifact.

## Ranking and integration choices

Both matchers round substantive metrics to 12 decimal places for ordering and
tie reporting. The common `decision_service/ranking.py` helper counts primary
keys once with a `Counter` and assigns dense ranks in policy order: O(n) time and
O(k) storage for k score groups. It replaces a complete rescan per distinct
group, without merging the two matchers' different feasibility/utility rules.
Cost, start time and stable ID order equally suitable candidates; they do not
make a tied candidate substantively better. Offset-aware timestamps compare
actual instants, including equivalent instants written in different timezones.

The service execution adapter derives `estimated_cost_minor` from the confirmed
`max_cost` fact using the frozen currency, cost scope and minor-unit precision.
This is done after scenario expansion so each scenario uses its own confirmed
cost evidence. Missing, estimated or unknown facts do not become zero-cost
options. An amount that cannot be represented exactly returns `invalid_input`
with `INVALID_OPTION_COST`; rounding or currency conversion could change a
winner without supporting evidence. The display price column is never a source.

Older stored runs are not reranked. When tie metadata is absent, the view derives
it from stored aggregate scores and the stored objective, preserving their
winner, display order and payload. Historical scheduled titles can be recovered
from the stored preparation. Missing metadata is not reconstructed from mutable
current plan data. New executions have a new source implementation hash, so they
cannot reuse an earlier implementation's cached run as a new calculation.

## Versioning and verification

New fields may be added to the view. Existing field meanings and the
privacy boundary require a new schema version if changed incompatibly.

Presentation fixtures live in
`decision_service/fixtures/presentation/recommendation_view_cases.json`. They
cover ranked results with and without a Pareto trade-off, blocked results awaiting
option facts or responses, no-feasible-candidate, pending, setup-review, and
failed states. The corresponding regression test is in
`decision_service/tests/test_service_integration.py`.

The machine-readable contract is
[`contracts/api.schema.json`](../../contracts/api.schema.json), including the
view, ranked candidate, Pareto alternative, unavailable candidate and optional
schedule/scenario fields. These view objects reject undeclared properties, so
adding private data accidentally fails contract validation. JSON Schema checking
is a test dependency only; no schema library or validation work is added to the
production request path. CI installs `decision_service/requirements-test.txt`.

`tests/test_recommendation_contract.py` covers confirmed cost mapping across
currency precisions, unconfirmed costs, precision rejection, scenario costs/date
windows, mixed timezone offsets, scheduled and historical ties, whole-response
privacy and positive/negative schema validation. Connected HTTP tests also check
cost ties, scheduled titles/times/ties and privacy for organisers and members.

Verified locally on 2026-10-19: 343 Decision tests passed with PostgreSQL enabled
(including eight new contract regressions); 14 connected HTTP journeys passed;
22 structured evaluation cases passed all 116 assertions. The rebuilt API,
background worker, preview worker and other running Compose services were healthy.
The efficiency smoke check retained one-statement completed reads and readiness
probes. These checks use synthetic inputs and do not call Gemini or validate its
live search results.
