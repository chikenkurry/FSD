# Processing challenge: recorded evaluation

Run on 8 October 2026 with processing `sparse-v7` and local
`qwen3:4b-instruct`. Inputs and labels are in
[processing_challenge.json](../../processing_challenge.json).

| Run | Cases passed | Assertions passed | Operational errors |
| --- | --- | --- | --- |
| [Structured rules](structured.json) | 20/20 | 64/64 | 0 |
| [All rules](rules.json) | 20/24 | 66/78 | 0 |
| [Live local Qwen](live.json) | 22/24 | 72/78 | 0 |
| [Frozen replay](replay.json) | 22/24 | 72/78 | 0 |

The live run made five calls in 60.7 seconds. Reports retain raw replies and
failures. The `evidence` directory freezes the v7 run for historical inspection.
Current processing rejects these stale artifacts. Use the newer
`recorded/refactor_v11/challenge/evidence` directory for current-version replay.

The recorded v7 replay exited 1 because two cases failed:
`printer-natural-quiet-direction` and
`warehouse-natural-capacity-direction`. The model marked soft comparisons hard;
grounding rejected the unsupported requirements and requested clarification.

Labels were written before evaluating these cases, but by the same agent doing
implementation work. Independent human review is **pending**. These results are
challenge/regression evidence, not independent or held-out accuracy claims.
Expected labels were not adjusted to eliminate model failures. Dataset hashes,
authorship, and review status are preserved in each report.
