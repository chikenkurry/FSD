"""Measure rules-only preprocessing and matching; no external API calls."""
from copy import deepcopy
import json
from pathlib import Path
import statistics
import time

from decision_service.service.execution import execute_preparation
from decision_service.service.snapshots import map_snapshots
from decision_service.preprocessing import preprocess

ROOT = Path(__file__).resolve().parents[1]


def fixture(members, options):
    planning = json.loads((ROOT / "decision_service/fixtures/preprocessing/planning_generic.json").read_text())
    replies = json.loads((ROOT / "decision_service/fixtures/preprocessing/response_generic.json").read_text())
    planning.update(schema_version="planning-snapshot-v1", plan_id="benchmark", option_revision=1, currency_minor_digits=2)
    templates = planning["options"]
    planning["options"] = [{**deepcopy(templates[i % len(templates)]), "option_id": f"option-{i}"} for i in range(options)]
    planning["roster"] = [f"member-{i}" for i in range(members)]
    participants = [{**deepcopy(replies["participants"][0]), "participant_id": pid} for pid in planning["roster"]]
    response = {"schema_version": "response-snapshot-v2", "plan_id": planning["plan_id"],
                "round_id": planning["round_id"], "option_revision": 1, "option_snapshot_id": planning["option_snapshot_id"],
                "snapshot_id": f"benchmark-{members}-{options}", "currency": planning["currency"], "minor_digits": 2,
                "participants": participants, "constraints": [{"participant_id": pid} for pid in planning["roster"]]}
    return planning, response


def main():
    report = []
    for members, options in ((2, 2), (10, 4), (30, 8)):
        inputs = fixture(members, options)
        timings = {"snapshot_mapping_ms": [], "preprocessing_ms": [], "matching_ms": []}
        for _ in range(20):
            start = time.perf_counter()
            plan, response = map_snapshots(*inputs)
            mapped = time.perf_counter()
            processed = preprocess(plan, response)
            prepared = time.perf_counter()
            if processed.get("preparation", {}).get("status") != "ready":
                raise SystemExit("Benchmark fixture did not prepare")
            result = execute_preparation(processed["preparation"], plan, inputs[1])
            matched = time.perf_counter()
            if result["status"] != "ranked":
                raise SystemExit("Benchmark fixture did not rank")
            for key, value in zip(timings, (mapped-start, prepared-mapped, matched-prepared)):
                timings[key].append(value * 1000)
        report.append({"members": members, "options": options,
                       **{key: round(statistics.median(values), 3) for key, values in timings.items()}})
    print(json.dumps({"mode": "rules_only", "iterations": 20, "results": report}, indent=2))


if __name__ == "__main__":
    main()
