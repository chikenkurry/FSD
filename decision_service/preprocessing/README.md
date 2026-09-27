# Decision preprocessing prototype

Run from the `FSD` repository root with Python 3.10 or later. The module uses only the Python standard library.

```sh
python3 -m decision_service.preprocessing
python3 -m unittest discover -s decision_service/tests -v
```

The first command reads the mock option and response snapshots in `decision_service/fixtures/preprocessing/` and prints a `PreprocessingResult`. The folder also contains `expected_algorithm_input.json`, the frozen handoff object for the teammate implementing the matcher, and `expected_checks.json`, the independent semantic checks used by tests. You can supply your own frozen snapshots with `--planning path.json --responses path.json`.

Call the pure function directly when integrating:

```python
from decision_service.preprocessing import preprocess

result = preprocess(option_snapshot, response_snapshot)
if result["status"] == "ready":
    recommendation = evaluate(result["algorithm_input"])
else:
    show_issues(result["issues"])
```

`ready` means required responses have usable interpretations. Activity facts can still be explicitly `unknown`, leaving the matcher to classify affected candidates as unresolved. `needs_clarification` means a member answer, roster, or semantic interpretation needs attention. `invalid_input` means the snapshots or question configuration violate the contract. In both latter cases `algorithm_input` is `null`.

The input shape and output fields are documented in [algorithm-input-shape.md](../algorithm-input-shape.md). The fixture covers structured availability/budget/ratings and open requirements/preferences. The current extractor recognizes explicit SGD amounts, unlimited budgets, and a controlled attribute vocabulary: `vegetarian_option`, `step_free_access`, `indoor`, and `quiet`. Unrecognized or ambiguous open answers produce issues. It does not interpret arbitrary new questions. An LLM extractor can later replace the rules in `extractors.py` while retaining the validation and output contract.

Question weights apply to soft questions only. All leader weights must be supplied together and sum to a positive number before normalization; otherwise all soft questions receive equal weights. Multiple extracted preferences from one question share that question's weight. The matcher must average their utilities for that question before applying the question weight. Hard constraints have a `null` score weight.

The selected policy versions are in `context`. Cache or persist the accepted processed input against both snapshot IDs and the processing/policy versions before invoking the matcher. This avoids reinterpreting the same frozen text differently on a retry.

The two service teams still need to agree on the immutable snapshot fields for questions, leader weights, and open answers. This prototype defines the Decision Service's expected adapter input; it does not provide a public API or network snapshot fetcher.
