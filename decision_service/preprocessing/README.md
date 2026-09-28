# Decision preprocessing prototype

## Sparse decisions (generic option path)

The `sparse-v2` path accepts option names and leader-written questions for any
decision. Pass `options` instead of `activities` to select it. The grad-trip
fixture is one example:

```sh
python3 -m decision_service.preprocessing \
  --planning decision_service/fixtures/preprocessing/planning_grad_trip.json \
  --responses decision_service/fixtures/preprocessing/response_grad_trip.json
```

The fixture has the four countries and six questions from the grad-trip example.
Service fields (`round_id`, snapshot IDs, revision, roster, and response status)
still identify the immutable inputs. `currency` and `cost_scope` define a budget
comparison; both are needed when members specify a maximum spend. Any other
decision details, such as a departure city, belong in the optional `context`
object. The preprocessing code does not require travel details.
Questions accept `question_id`/`label` (or `id`/`text`) and optional `choices`
as strings or `{choice_id, label}` objects. A leader may provide `role`,
`criterion`, and soft `relevance` explicitly. With a configured model,
`classify_question` assesses every question against the decision goal and
option facts. Without a model, a small domain-independent rules fallback
recognizes common availability, budget, duration, and preference wording;
unrecognized questions remain `unclassified` and provisional; their answers
are preserved in `unclassified_answers` without a scoring weight. Answers use the existing
`participants[].answers[]` envelope. Availability accepts text containing one
or two ISO dates (`2027-06-01 to 2027-06-12`) or
`[{"start_date":"2027-06-01","end_date":"2027-06-12"}]`. Numeric budget and
duration choices, `Unlimited`, and `Fine with anything` are normalized locally.
Vague dates such as “sometime in December” produce a clarification issue.

Open answers use `extract_sparse_answer`, which can
return several preferences with exact answer substrings as evidence. Natural
language dates can use `extract_sparse_dates` when the answer states a year. A model
claim that an answer contains a must-have is marked `needs_confirmation`; it
does not become an enforced hard constraint. Without a provider or saved
semantic evidence, open meaning stays unresolved. Model calls are tested with
fakes; no live model is exercised by the test suite.

The same question can receive different roles in different decisions. The
tests classify “Favourite Subject” as informational for a country trip and as
a soft criterion for choosing a subject-themed museum exhibit. A laptop
purchase test reaches `ready` without any date or travel fields.

`algorithm_input.context.schema_version` is `sparse-v2`. Its option-level
`candidates` have `facts`, `missing_criteria`, and `tag_suggestions`. A model
can suggest plausible tags relevant to soft questions, but they remain hypotheses and
do not satisfy a missing fact. A supplied fact uses
`{criterion, value, status: "confirmed"|"estimated", source, unit?, context?}`.
When a decision has both availability and duration questions, `scenario_requests`
contains each option and feasible duration with the start-date range shared by
the group. These are compact requests for scenario-specific evidence. An evidence collector can
put sourced `planning.scenario_costs` records back into the immutable planning
snapshot, matching `option_id`, `duration_days`, and the start-date range.
Each record needs `amount`, `currency`, `scope`, `status`, and `source`; its scope
must match `planning.cost_scope`. For decisions without date/duration scenarios,
cost may be a sourced option fact using criterion `max_cost`, a currency `unit`,
and `context.scope`. Estimated costs keep a hard budget check provisional. Option facts
can contain a list of tags, for example `personal_interests: ["hiking",
"museums"]`, with a source and confirmation status. Question roles, reasons,
and soft weights are in `scoring_model.questions`. Constraints, preferences,
and informational answers are separate.

The sparse path returns `provisional` while source-backed option or scenario
facts are missing, costs are only estimated, or open answers still need
extraction. It returns
`needs_clarification` for unusable member answers, `invalid_input` for a bad
snapshot, and `upstream_unavailable` for a failed configured model. Unlike the
older activity path, a provisional/clarification result retains the partial
`algorithm_input` for review. Only a `ready` sparse result can be treated as a
complete comparison input. The existing activity/time matcher contract is
**not** compatible with `sparse-v2`; a generic matcher must consume the new
schema. The preprocessing path does not retrieve live external facts or
rank options.

The `semantic_evidence` returned after model extraction can be saved and
replayed with `--semantic-evidence`; replay validates the snapshot IDs and
processing version.

Run from the `FSD` repository root with Python 3.10 or later. The module uses only the Python standard library.

```sh
python3 -m decision_service.preprocessing
python3 -m unittest discover -s decision_service/tests -v
```

The first command reads the mock option and response snapshots in `decision_service/fixtures/preprocessing/` and prints a `PreprocessingResult`. The folder also contains `expected_algorithm_input.json`, the frozen handoff object for the teammate implementing the matcher, and `expected_checks.json`, the independent semantic checks used by tests. You can supply your own frozen snapshots with `--planning path.json --responses path.json`.

To see deterministic calculated weights without leader values, run:

```sh
python3 -m decision_service.preprocessing --planning decision_service/fixtures/preprocessing/planning_auto_weights.json
```

In that example, activity ratings receive weight `0.6667` and the environment question receives `0.3333`, because the two activities have different known indoor values. The matcher calculates individual member-to-candidate fits from this handoff.

To assess **every unweighted soft question against the decision goal** with the local model, run the Ollama sidecar from the repository root:

```sh
docker compose -f decision_service/compose.yaml up -d ollama
docker compose -f decision_service/compose.yaml exec ollama ollama pull qwen3:4b-instruct
docker compose -f decision_service/compose.yaml run --build --rm preprocessing-demo
```

The last command uses `planning_auto_weights.json` and should return `ready`, with `weight_source: "model_relevance"` on both soft questions. The [Qwen model package](https://ollama.com/library/qwen3%3A4b-instruct) is about 2.5 GB. The Ollama service keeps it in a named volume; no model files are committed to the repository. The Compose service uses Docker's internal network and does not bind host port `11434`, so it can coexist with a native Ollama process. The provider calls Ollama's local `/api/chat` endpoint with [JSON schemas](https://docs.ollama.com/capabilities/structured-outputs) and temperature zero. The CLI can also reach an existing Ollama server:

```sh
python3 -m decision_service.preprocessing --semantic-provider ollama \
  --planning decision_service/fixtures/preprocessing/planning_auto_weights.json
```

Set `OLLAMA_BASE_URL` or pass `--ollama-url` if it is not on `http://localhost:11434`. You can override the default `qwen3:4b-instruct` with `--model`. A planning snapshot should provide `decision_question`; the provider falls back to the plan description, title, or a generic group-choice goal when it is absent. The model sees the question, plan goal, and option facts when calculating relevance, **not member answers**. With no model provider, the existing deterministic option-relevance heuristic still runs.

If the Compose model pull fails because the container does not trust your network's TLS certificate, pull through native Ollama and copy its verified model cache into the running container:

```sh
ollama pull qwen3:4b-instruct
docker cp ~/.ollama/models/. decision_service-ollama-1:/root/.ollama/models/
docker compose -f decision_service/compose.yaml exec ollama ollama list
```

The native and container servers have separate model caches. You can instead run `python3 -m decision_service.preprocessing --semantic-provider ollama ...` on the host against native Ollama. Do not disable certificate verification to work around a failed pull.

Call the pure function directly when integrating:

```python
from decision_service.preprocessing import preprocess

result = preprocess(option_snapshot, response_snapshot)
if result["status"] == "ready":
    recommendation = evaluate(result["algorithm_input"])
else:
    show_issues(result["issues"])
```

`ready` means required responses have usable interpretations. Activity facts can still be explicitly `unknown`; the matcher decides how that affects feasibility or scoring. `needs_clarification` means a member answer, roster, or semantic interpretation needs attention. `invalid_input` means the snapshots, question configuration, or supplied model assessment violate the contract. `upstream_unavailable` means an optional model call failed and may be retried. Only `ready` includes `algorithm_input`.

The input shape and output fields are documented in [algorithm-input-shape.md](../algorithm-input-shape.md). The fixture covers structured availability/budget/ratings and open requirements/preferences. The local extractor recognizes explicit SGD amounts, unlimited budgets, and a controlled attribute vocabulary: `vegetarian_option`, `step_free_access`, `indoor`, and `quiet`. Unrecognized or ambiguous local answers produce issues.

For an answer outside that vocabulary, use `kind: "semantic_preference"` or `"semantic_requirement"`. It accepts `answer_format: "text"` or `"choice"`; a choice question declares `choices: [{"choice_id": "...", "label": "..."}]`, and a member answer supplies `{"choice_id": "..."}`. Add factual option `description` and/or known `attributes` for the matcher to use later. To exercise semantic extraction locally, after pulling the model run:

```sh
docker compose -f decision_service/compose.yaml run --rm preprocessing-demo \
  python -m decision_service.preprocessing --semantic-provider ollama \
  --planning decision_service/fixtures/preprocessing/planning_semantic.json \
  --responses decision_service/fixtures/preprocessing/response_semantic.json
```

The optional hosted provider remains available:

```sh
export OPENAI_API_KEY=your_key
python3 -m decision_service.preprocessing --semantic-provider openai --planning your_options.json --responses your_responses.json
```

Both providers use structured outputs. They assess generic semantic questions and, when a model is configured, all soft questions missing a leader weight. Only generic questions use the model to interpret participant answers; supported structured and open answers still follow the local extractors. Question relevance must be in `[0,1]`. Each resolved answer interpretation includes a criterion, value, meaning, and exact substring from the member answer as evidence. The answer extractor does not receive candidates. The automated tests mock both provider transports; they do not run a live model.

You can inspect the generic question handoff offline using reviewed example evidence:

```sh
python3 -m decision_service.preprocessing \
  --planning decision_service/fixtures/preprocessing/planning_semantic.json \
  --responses decision_service/fixtures/preprocessing/response_semantic.json \
  --semantic-evidence decision_service/fixtures/preprocessing/semantic_evidence.json
```

This example includes a structured travel choice and an open ramp requirement. The saved evidence lets it run without an API key.

The handoff contains `candidates`, normalized `constraints` and `preferences`, `semantic_interpretations`, and `scoring_model.questions` with weights. It contains no pass/fail or fit per candidate. The teammate's matcher compares each member's data against candidates, checks hard requirements, computes soft fit, and ranks feasible outcomes.

Question weights apply to soft questions only. A supplied leader weight is used for that question. With a configured model, every missing soft weight uses question relevance assessed from the decision goal and option facts. Without a model, the deterministic baseline assigns rating relevance `1` and estimates attribute relevance from known option facts. The raw values are normalized to sum to 1. Multiple extracted preferences from one question share one question weight. Hard constraints have a `null` score weight. These calculated weights estimate decision usefulness; they do not infer personal importance. The source is recorded as `leader`, `model_relevance`, or `auto_relevance`.

The selected policy versions, model name, and semantic artifact hash are in `context`. Persist the accepted `algorithm_input` and returned `semantic_evidence` against both snapshot IDs and the processing/policy versions before invoking the matcher. On a retry, call `preprocess(option_snapshot, response_snapshot, semantic_evidence=saved_evidence)`; it validates the snapshot references and reuses the same interpretation without calling a model. Model-based extraction still needs a review workflow and evaluation examples before use with real groups.

The two service teams still need to agree on the immutable snapshot fields for questions, leader weights, and open answers. This prototype defines the Decision Service's expected adapter input; it does not provide a public API or network snapshot fetcher.
