"""Build aggregate results and member-specific reviews from private run artifacts."""
from copy import deepcopy

from .snapshots import SnapshotError


def public_result(run: dict) -> dict:
    result = deepcopy(run.get("result", {}))
    preparation = run.get("processing", {}).get("preparation", {})
    facts = [{key: row[key] for key in ("option_id", "attribute_id", "value_type", "unit", "priority") if key in row}
             for row in preparation.get("fact_requests", [])]
    scenarios = [{key: row[key] for key in ("option_id", "duration_days", "earliest_start_date", "latest_start_date", "cost_evidence_status") if key in row}
                 for row in preparation.get("scenario_requests", [])]
    return {"run_id": run["run_id"], "status": run["status"], "input_refs": run["input_refs"],
            **({"collection": deepcopy(run["collection"])} if "collection" in run else {}),
            "job_state": run.get("job_state", "completed"),
            "execution_specification": run.get("execution_specification", {}),
            "result": result, "fact_requests": facts, "scenario_requests": scenarios,
            "issues": [{"code": issue.get("code", "PROCESSING_ISSUE")} for issue in run.get("issues", [])]}


def member_review(run: dict, member_id: str) -> dict:
    if member_id not in run.get("member_states", {}):
        raise SnapshotError("Member is not in this run")
    packet = run.get("processing", {}).get("preparation", {})
    own = {key: [deepcopy(row) for row in packet.get(key, []) if row.get("participant_id") == member_id]
           for key in ("constraints", "preferences", "importance", "unclassified_answers")}
    issues = []
    prefix = f"responses.participants.{member_id}."
    for issue in run.get("issues", []):
        path = issue.get("path", "")
        if path.startswith("responses.participants.") and not path.startswith(prefix):
            continue
        record = {"code": issue["code"]}
        if path.startswith(prefix):
            record["message"] = issue.get("message", "Review this answer")
            if ".answers." in path:
                record["question_id"] = path.split(".answers.", 1)[1]
        issues.append(record)
    own.update(status=run["status"], response_status=run["member_states"][member_id], issues=issues,
               run_id=run.get("run_id"), response_revision=run.get("response_revision"))
    return own
