"""Validate frozen inputs and preprocess them before invoking a supported matcher."""
from decision_service.preprocessing import preprocess

from .execution import execute_preparation
from .snapshots import map_snapshots
from .views import member_review, public_result


def execute(planning: dict, responses: dict, *, semantic_provider=None) -> dict:
    plan, reply = map_snapshots(planning, responses)
    refs = {key: planning[key] for key in ("plan_id", "round_id", "option_revision", "option_snapshot_id")}
    refs["response_snapshot_id"] = responses["snapshot_id"]
    incomplete = [p for p in reply["participants"] if p["response_status"] != "complete"]
    member_states = {p["participant_id"]: p["response_status"] for p in reply["participants"]}
    if incomplete:
        return {"status": "blocked", "input_refs": refs, "member_states": member_states,
                "issues": [{"code": "STALE_RESPONSE" if p["response_status"] == "stale" else "INCOMPLETE_RESPONSE"} for p in incomplete]}
    if responses.get("preferences"):
        return {"status": "unsupported", "input_refs": refs, "member_states": member_states,
                "issues": [{"code": "ACTIVITY_RATINGS_NOT_SUPPORTED"}]}
    policy = {"group_objective": plan["group_objective"]} if plan.get("group_objective") else None
    processed = preprocess(plan, reply, policy=policy, semantic_provider=semantic_provider)
    packet = processed.get("preparation")
    base = {"input_refs": refs, "processing": processed, "member_states": member_states}
    if not packet or packet["status"] != "ready":
        return {**base, "status": packet["status"] if packet else processed["status"], "issues": processed["issues"]}
    return {**base, **execute_preparation(packet, plan, responses)}
