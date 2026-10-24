# Natural-language improvements: recorded results

Final processing: `sparse-v10`; canonical label policy: `scoped-labels-v3`.
Recorded on 8 October 2026 with local `qwen3:4b-instruct`.
These are historical live results. Current `sparse-v11` rejects the old evidence;
use `recorded/refactor_v11` for current recorded-response regression and replay.

| Dataset | Live cases | Live assertions | Seconds | Model calls | Replay |
| --- | --- | --- | --- | --- | --- |
| [Development v5](development/live.json) | 34/34 | 185/185 | 87.8 | 12 | [34/34](development/replay.json) |
| [Processing challenge](challenge/live.json) | 24/24 | 78/78 | 57.1 | 5 | [24/24](challenge/replay.json) |
| [Language follow-up](followup/live.json) | 8/10 | 21/24 | 98.4 | 10 | [8/10](followup/replay.json) |

All final runs had zero operational errors. The original two comparative failures
and the programming/coding synonym passed. Regression tests also feed the original
rejected model replies through the current pipeline, avoiding dependence on a
fresh model returning the same mistake.

The follow-up set's two failures remain visible:

- `outdoors-specific-activity`: the model suggested a broader outdoor category
  while saying unresolved. Processing requested clarification and did not merge.
- `venue-opposite-atmosphere`: the model treated noisy/busy as equivalent. The
  target is valid structurally but the equivalence is semantically incorrect.
  The preference remains marked as an estimated model interpretation. Structural
  validation cannot prove a synonym judgment is true.

Inputs and expected meanings were not changed to remove failures. The follow-up
set was authored before its first execution, then used to diagnose and improve
general label/comparative handling. It is now development evidence, not held-out
data. Independent human label review remains pending.

`initial_v8` preserves three earlier reports, including 5/10 follow-up results.
`initial_v9` preserves a 34/34 development run and a challenge run with a timed-out
provider call (23/24, one operational error). Those reports are retained rather
than silently replacing failed or unavailable calls. Current processing rejects
older-version evidence. Earlier intermediate artifacts also remain in the
neighboring `language_v9` directory.

Each dataset directory contains accepted evidence from its v10 run. The following
commands describe replay with that processing version, not the current pipeline:

```sh
python3 -m decision_service.evaluation \
  --evidence-dir decision_service/fixtures/evaluation/recorded/language_v10/development/evidence

python3 -m decision_service.evaluation \
  --dataset decision_service/fixtures/evaluation/processing_challenge.json \
  --evidence-dir decision_service/fixtures/evaluation/recorded/language_v10/challenge/evidence

python3 -m decision_service.evaluation \
  --dataset decision_service/fixtures/evaluation/language_followup.json \
  --evidence-dir decision_service/fixtures/evaluation/recorded/language_v10/followup/evidence
```

The follow-up command exits 1 because two labelled cases fail; development and
challenge replay exit 0. Full reports retain dataset hashes, issues, and raw
model replies. These small synthetic results do not establish general accuracy
or repeated live-call stability.
