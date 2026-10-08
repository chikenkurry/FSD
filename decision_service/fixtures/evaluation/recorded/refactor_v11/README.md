# Refactor regression evidence

Processing: `sparse-v11`. These runs used previously recorded model replies
through a test provider. They made no live inference requests and do not measure
new model accuracy.

| Dataset | Cases passed | Assertions passed | Report |
| --- | --- | --- | --- |
| Development | 34/34 | 185/185 | [regression.json](development/regression.json) |
| Challenge | 24/24 | 78/78 | [regression.json](challenge/regression.json) |
| Follow-up | 8/10 | 21/24 | [regression.json](followup/regression.json) |

Raw replies came from `recorded/language_v10`. They were supplied through the
current public preprocessing API, which validated and emitted new v11 evidence.
Older evidence files were not edited to bypass the version checks. Current
saved artifacts identify their model as `recorded:qwen3:4b-instruct` or recorded
rules. Both known follow-up failures remain: hiking/outdoor ambiguity and the
incorrect noisy/busy equivalence. Independent human review remains pending.

Replay the current challenge artifacts from `FSD`:

```sh
python3 -m decision_service.evaluation \
  --dataset decision_service/fixtures/evaluation/processing_challenge.json \
  --evidence-dir decision_service/fixtures/evaluation/recorded/refactor_v11/challenge/evidence
```

Use `development/evidence` with the default dataset, or `followup/evidence` with
`language_followup.json`, for the other sets. Follow-up replay exits 1 because
its two labelled cases still fail.
