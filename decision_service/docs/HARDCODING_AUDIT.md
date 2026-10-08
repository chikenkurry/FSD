# Preprocessing hardcoding audit

Scope: `decision_service/preprocessing`, its handoff policies in `contract.py`,
provider transport, and the preprocessing CLI. Inspected on 8 October 2026.
Updated after the hardcoding cleanup. This is a source review of fixed behavior,
not a claim that every input meaning has been evaluated.

## Removed and simplified

- Removed the generic 365-day ceiling. `durations.py` validates positive whole-day
  targets; ranges retain their numeric endpoints. `scenarios.py` clips enumeration
  to shared availability and limits output through `policy.max_scenario_requests`
  (default 10,000). Infeasible long durations produce no scenario.
- Removed SGD-only open-budget extraction. Both paths use `money.py` for currency
  checks and exact amount parsing. The activity path accepts
  `planning.currency_minor_digits` for conversion to integer minor units; its
  compatibility default is 2. Callers must declare a different precision when
  their currency requires it. Excess precision requests clarification, not rounding.
- Consolidated currency-symbol handling and `k` expansion. The symbol meanings
  remain defined because a bare symbol does not uniquely identify a currency.
- Moved scenario generation out of `sparse.py`, separated numeric interpretation
  from requirement compilation, and reused the shared issue constructor.

These changes use `sparse-v11` and `semantic-v6`. Older evidence is rejected.
The refactor was checked with saved model replies and rule-based tests; it did
not implement source retrieval or run a new live-model accuracy benchmark.

The pipeline is a hybrid of fixed parsing/validation rules and optional semantic
interpretation. It is not entirely model-driven. The generic `planning.options`
path builds arbitrary typed criteria from supplied facts/declarations; it has
several reserved concepts. The older `planning.activities` path has more domain
assumptions. Neither library path imports the fixture prices, option names,
answers, or expected evaluation labels to produce results.

## Generic options path

| Fixed element | Location | Effect and configurability |
| --- | --- | --- |
| Reserved `availability`, `max_cost`, `duration_days` IDs and date/money/day units | [generic_mapping.py](../preprocessing/generic_mapping.py), [sparse.py](../preprocessing/sparse.py) | Those concepts have special validation and scenario handling. Other criteria are built from facts or `planning.criteria`. Aliases can point to existing canonical criteria; the reserved concepts themselves are fixed. |
| Schedule handling uses inclusive calendar-date availability and whole-day durations | [generic_answers.py](../preprocessing/generic_answers.py), [sparse.py](../preprocessing/sparse.py), [generic_preparation.py](../preprocessing/generic_preparation.py) | The generic scenario helper is not an arbitrary scheduling engine for every unit/date criterion. Availability has a dedicated answer path; embedded compound dates and general date-valued option facts are not supported by the numeric/text registry. |
| English budget/date/duration/preference and importance phrases | [sparse.py](../preprocessing/sparse.py), [member_importance.py](../preprocessing/member_importance.py) | A known phrase can determine the role without a model; e.g. the budget fallback assumes a hard maximum. Leader role/criterion/mapping declarations can override this. Familiarity with a word is not complete semantic understanding. |
| English requirement, optionality, polarity, numeric-bound and comparative vocabulary | [generic_evidence.py](../preprocessing/generic_evidence.py), [generic_values.py](../preprocessing/generic_values.py), [comparatives.py](../preprocessing/comparatives.py) | This includes `must`, `need`, `under`, `higher`, etc. The new comparative repair uses grammatical templates and a finite direction vocabulary, not a list of specific failed answers or decision domains. It repairs only numeric meanings already bound by semantic extraction. Negation, bounded/compound comparisons remain outside that repair. No configurable language pack exists. |
| No-preference phrases, date formats and boolean text values | [generic_answers.py](../preprocessing/generic_answers.py), [generic_mapping.py](../preprocessing/generic_mapping.py) | Exact English indifference phrases and ISO-style dates are recognized locally; other wording needs a provider or clarification. |
| Positive whole-day targets and inclusive calendar availability | [durations.py](../preprocessing/durations.py), [scenarios.py](../preprocessing/scenarios.py) | No fixed year-length ceiling remains. Integer scenario durations are bounded by actual shared windows and the configured scenario-count limit. |
| Currency-symbol meanings and `k` shorthand | [money.py](../preprocessing/money.py) | Shared by generic and activity parsers. Currency comes from the plan; symbols are checked against it. No currency conversion occurs. |
| Supported types, formats, roles and comparison-rule IDs | [generic_mapping.py](../preprocessing/generic_mapping.py), [semantics.py](../preprocessing/semantics.py), [sparse.py](../preprocessing/sparse.py) | Intentional schema/application contract. A model cannot invent an executable comparison rule. Extending these requires a versioned change and algorithm agreement. |
| Default rule relevance 0.5 for recognized soft questions | [generic_mapping.py](../preprocessing/generic_mapping.py), [sparse.py](../preprocessing/sparse.py) | A baseline policy, not a measurement of personal importance. Leader weights/relevance can override it; repeated automatic topics share question mass. |
| Equal question mass split between criteria, default importance 1, longest-path ordinal tiers, 12-digit weight rounding | [member_importance.py](../preprocessing/member_importance.py) | Explicit numeric member importance is supported. Splitting and ordinal-tier policy implementations are fixed and versioned, rather than dynamically selected. |
| Numeric target scale uses confirmed option spread unless a leader scale is supplied | [generic_mapping.py](../preprocessing/generic_mapping.py) | The **policy** is fixed, but its scale value is derived from supplied data, not a hardcoded battery/cost value. Direction bounds are also data-derived. |
| At most 20 extracted meanings/importance relations; finite numeric bounds | [semantics.py](../preprocessing/semantics.py), [generic_mapping.py](../preprocessing/generic_mapping.py), [member_importance.py](../preprocessing/member_importance.py) | Validation/resource limits, not domain facts. The interpretation limit and numeric caps are not exposed as policy settings. |
| Every member in the generic roster is required | [sparse.py](../preprocessing/sparse.py) | Generic preparation exports `is_required_for_decision: true` for the whole roster and intersects availability across that roster. Optional member participation is not configured on this path. |

## Older activity/time path

| Fixed element | Location | Effect and configurability |
| --- | --- | --- |
| Four open-text attribute mappings: `vegetarian_option`, `step_free_access`, `indoor`, `quiet`, and their synonyms/opposites | [extractors.py](../preprocessing/extractors.py) | The local open-preference/open-requirement rules are limited to these attributes. Other supplied typed attributes can use structured data or explicit semantic bindings. These dictionaries do not drive the generic options path. |
| Integer minor-unit budgets | [extractors.py](../preprocessing/extractors.py), [money.py](../preprocessing/money.py) | The SGD restriction is removed. Currency and minor-unit precision come from the plan, with a two-digit compatibility default. |
| `yes`/`no` legacy values and activity ratings 0–4 | [pipeline.py](../preprocessing/pipeline.py), [normalization.py](../preprocessing/normalization.py) | Part of the existing activity contract; not an arbitrary numeric utility scale. |
| 30-minute default grid and minimum activity duration, 14-day window limit, 10,000-candidate cap | [candidates.py](../preprocessing/candidates.py) | The candidate-builder helper accepts a grid argument, but the activity preprocessing entry point always uses the default. Minimum duration, maximum window and cap are fixed limits. |
| Exactly one availability question and at least one budget question; model-assisted runs capped at 100 candidates | [pipeline.py](../preprocessing/pipeline.py) | These are enforced activity/time assumptions and resource limits. They do not apply to generic option decisions without date/budget questions. |
| Coverage/distinction relevance formula with 0.25/0.75 constants and uniform no-relevance fallback | [weights.py](../preprocessing/weights.py) | Legacy relevance policy. Leader weights override question weights; these formula constants are fixed. |

## Shared defaults and external boundaries

- `contract.py` defaults to `maximin_then_average`, contains 0.6/0.4 group-score
  coefficients, and fixes cost/start-time/stable-ID tie breakers. Group objective
  fields can be supplied through `policy.group_objective`; the coefficients are
  not member-importance ratios and preprocessing does not compute those scores.
- `semantics.py` contains fixed prompt instructions and illustrative examples,
  model defaults, timeout defaults, the OpenAI endpoint and Ollama's default
  localhost endpoint. Model/server settings can be overridden. Ollama sampling
  temperature is fixed at zero; this does not establish repeat-run stability.
- `__main__.py` defaults to demo fixture paths **only when CLI input arguments
  are omitted**. `preprocess(planning, responses)` uses its supplied snapshots;
  it does not fall back to fixture answers.
- Schema versions, label policy versions, issue codes, provenance requirements,
  and confirmation rules are fixed contracts. Keeping them deterministic is
  necessary for validation and replay.

There is no runtime global `programming → coding` synonym dictionary. Declared
aliases are supplied in the planning snapshot and are criterion-scoped. Otherwise
the model assesses ordinary contextual equivalence against existing targets.
Option facts are normalized only with formatting and declared aliases; model
assessments never turn a synonym or a description into an option fact.

## Suggested priorities

1. Define approved currency metadata and source acceptance rules before adding
   automatic fact collection. See [FACT_COLLECTION_PROPOSAL.md](FACT_COLLECTION_PROPOSAL.md).
2. Keep an explicit distinction between generic and activity contracts; use the
   generic path for arbitrary criteria rather than extending the legacy four-word
   attribute dictionary for every new decision domain.
3. Version and evaluate English parsing changes, preserve model uncertainty, and
   use reviewed aliases for equivalences that must be deterministic.
4. Review weighting/scale assumptions jointly with the algorithm implementer.
   Removing schemas and validation limits would not make the system more generic.

Language rules, schema definitions, confirmation requirements and weighting
policies remain because they are used by current processing. The refactor does
not replace those contracts with unvalidated model output.
