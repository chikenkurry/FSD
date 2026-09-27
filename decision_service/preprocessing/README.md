# Decision preprocessing prototype

Run from the `FSD` repository root with Python 3.10 or later. The module uses only the Python standard library.

```sh
python3 -m decision_service.preprocessing
python3 -m unittest discover -s decision_service/tests -v
```

The first command reads the mock option and response snapshots in `decision_service/fixtures/preprocessing/` and prints a `PreprocessingResult`. The folder also contains `expected_algorithm_input.json`, the frozen handoff object for the teammate implementing the matcher, and `expected_checks.json`, the independent semantic checks used by tests. You can supply your own frozen snapshots with `--planning path.json --responses path.json`.

To see calculated weights without leader values, run:

```sh
python3 -m decision_service.preprocessing --planning decision_service/fixtures/preprocessing/planning_auto_weights.json
```

In that example, activity ratings receive weight `0.6667` and the environment question receives `0.3333`, because the two activities have different known indoor values. The output also shows the individual member-to-candidate fits in `question_matches`.

Call the pure function directly when integrating:

```python
from decision_service.preprocessing import preprocess

result = preprocess(option_snapshot, response_snapshot)
if result["status"] == "ready":
    recommendation = evaluate(result["algorithm_input"])
else:
    show_issues(result["issues"])
```

`ready` means required responses have usable interpretations. Activity facts can still be explicitly `unknown`, making affected question comparisons unresolved. `needs_clarification` means a member answer, roster, or semantic interpretation needs attention. `invalid_input` means the snapshots, question configuration, or supplied model assessment violate the contract. `upstream_unavailable` means an optional model call failed and may be retried. Only `ready` includes `algorithm_input`.

The input shape and output fields are documented in [algorithm-input-shape.md](../algorithm-input-shape.md). The fixture covers structured availability/budget/ratings and open requirements/preferences. The local extractor recognizes explicit SGD amounts, unlimited budgets, and a controlled attribute vocabulary: `vegetarian_option`, `step_free_access`, `indoor`, and `quiet`. Unrecognized or ambiguous local answers produce issues.

For a question outside that vocabulary, use `kind: "semantic_preference"` or `"semantic_requirement"`. It accepts `answer_format: "text"` or `"choice"`; a choice question declares `choices: [{"choice_id": "...", "label": "..."}]`, and a member answer supplies `{"choice_id": "..."}`. Add factual option `description` and/or known `attributes` that let the semantic provider compare answers with each option. Select the optional OpenAI provider explicitly:

```sh
export OPENAI_API_KEY=your_key
python3 -m decision_service.preprocessing --semantic-provider openai --planning your_options.json --responses your_responses.json
```

The provider uses the [OpenAI Responses API structured output format](https://developers.openai.com/api/docs/guides/structured-outputs). It is called only for generic semantic questions. Results must name every supplied candidate, keep scores within `[0,1]`, and cite an exact substring from an option description or known attribute for every definitive comparison. An unsupported option fact remains unresolved. The local tests use a fake provider; a live model call requires an API key and was not part of the automated tests.

You can inspect the generic question handoff offline using reviewed example evidence:

```sh
python3 -m decision_service.preprocessing \
  --planning decision_service/fixtures/preprocessing/planning_semantic.json \
  --responses decision_service/fixtures/preprocessing/response_semantic.json \
  --semantic-evidence decision_service/fixtures/preprocessing/semantic_evidence.json
```

This example includes a structured travel choice and an open ramp requirement. The saved evidence lets it run without an API key.

The `question_matches` output contains one record for each member, candidate, and question. Hard questions have `pass`, `fail`, or `unresolved`; soft questions have a `fit` from 0 to 1 or `unresolved`. The matcher uses these records for feasibility and ranking. Normalized constraints and preferences remain in the output so the results can be explained and audited.

Question weights apply to soft questions only. A supplied leader weight is used for that question. For missing weights, preprocessing calculates option relevance: a rating question can distinguish activities; an attribute question gets a higher relevance when the attribute is known and differs across options; a generic question receives a model relevance based on its text, the context, and the options. The raw values are normalized to sum to 1. Multiple extracted preferences from one question share one question weight. Hard constraints have a `null` score weight. These calculated weights estimate decision usefulness; they do not infer personal importance.

The selected policy versions, model name, and semantic artifact hash are in `context`. Persist the accepted `algorithm_input` and returned `semantic_evidence` against both snapshot IDs and the processing/policy versions before invoking the matcher. On a retry, call `preprocess(option_snapshot, response_snapshot, semantic_evidence=saved_evidence)`; it validates the snapshot references and reuses the same interpretation without calling a model. Model-based extraction still needs a review workflow and evaluation examples before use with real groups.

The two service teams still need to agree on the immutable snapshot fields for questions, leader weights, and open answers. This prototype defines the Decision Service's expected adapter input; it does not provide a public API or network snapshot fetcher.
