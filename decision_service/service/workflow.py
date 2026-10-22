"""Validate frozen inputs and preprocess them before invoking a supported matcher."""
from copy import deepcopy
from decision_service.preprocessing import preprocess

from .enrichment import requested_facts
from .execution import execute_preparation, adapt_preparation
from .snapshots import map_snapshots
from .views import member_review, public_result


def _supplement_discovered_facts(planning, responses, processed, enrichment, *,
                                 initial_requests, fact_enricher, semantic_provider, policy):
    if fact_enricher is None or enrichment is None:
        return planning, processed, enrichment
    packet = processed.get("preparation") or {}
    if packet.get("status") != "needs_information" or not packet.get("fact_requests"):
        return planning, processed, enrichment
    extra, seen = [], set(initial_requests)
    for req in packet.get("fact_requests", []):
        key = (req.get("option_id"), req.get("attribute_id"))
        kind = req.get("value_type")
        if key not in seen and kind in {"number", "decimal", "category", "boolean", "tag_set"}:
            seen.add(key)
            extra.append({
                "option_id": req["option_id"],
                "attribute_id": req["attribute_id"],
                "value_type": kind,
                "unit": planning.get("currency") if req["attribute_id"] == "max_cost" else req.get("unit"),
            })
    if not extra:
        return planning, processed, enrichment
    planning, second = fact_enricher.enrich(planning, responses, extra_requests=extra)
    for field in ("applied_facts", "invalidated_facts", "collections", "issues"):
        enrichment[field].extend(second.get(field, []))
    if not second.get("applied_facts"):
        return planning, processed, enrichment
    plan, reply = map_snapshots(planning, responses)
    processed = preprocess(plan, reply, policy=policy, semantic_provider=semantic_provider)
    return planning, processed, enrichment


def execute(planning: dict, responses: dict, *, semantic_provider=None, fact_enricher=None) -> dict:
    plan, reply = map_snapshots(planning, responses)
    refs = {key: planning[key] for key in ("plan_id", "round_id", "option_revision", "option_snapshot_id")}
    refs["response_snapshot_id"] = responses["snapshot_id"]
    # Members left out by an early close are recorded but do not block ranking.
    incomplete = [p for p in reply["participants"] if p["response_status"] != "complete" and p.get("is_required_for_decision", True)]
    member_states = {p["participant_id"]: p["response_status"] if p.get("is_required_for_decision", True) else "not_counted"
                     for p in reply["participants"]}
    if incomplete:
        return {"status": "blocked", "input_refs": refs, "member_states": member_states,
                "issues": [{"code": "STALE_RESPONSE" if p["response_status"] == "stale" else "INCOMPLETE_RESPONSE"} for p in incomplete]}
    if responses.get("preferences"):
        return {"status": "unsupported", "input_refs": refs, "member_states": member_states,
                "issues": [{"code": "ACTIVITY_RATINGS_NOT_SUPPORTED"}]}
    enrichment = None
    initial_requests = set()
    if fact_enricher is not None:
        if planning.get("interpretation_policy") == "facts-v1" and planning.get("execution_mode", "options") == "options":
            initial_requests = {(r["option_id"], r["attribute_id"]) for r in requested_facts(planning, responses)}
        planning, enrichment = fact_enricher.enrich(planning, responses)
        plan, reply = map_snapshots(planning, responses)
    policy = {"group_objective": plan["group_objective"]} if plan.get("group_objective") else None
    processed = preprocess(plan, reply, policy=policy, semantic_provider=semantic_provider)
    planning, processed, enrichment = _supplement_discovered_facts(
        planning, responses, processed, enrichment,
        initial_requests=initial_requests, fact_enricher=fact_enricher,
        semantic_provider=semantic_provider, policy=policy)
    plan, reply = map_snapshots(planning, responses)
    packet = processed.get("preparation")
    base = {"input_refs": refs, "processing": processed, "member_states": member_states}
    if enrichment is not None:
        base["fact_enrichment"] = enrichment
    if not packet or packet["status"] != "ready":
        return {**base, "status": packet["status"] if packet else processed["status"], "issues": processed["issues"]}
    return {**base, **execute_preparation(packet, plan, responses)}


def preview(planning: dict, responses: dict, *, semantic_provider=None, fact_enricher=None) -> dict:
    """Interpret one member's current draft without ranking or freezing it."""
    if len(responses.get("participants", [])) != 1 or type(responses.get("response_revision")) is not int:
        from .snapshots import SnapshotError
        raise SnapshotError("A preview needs one member and an exact response revision")
    planning, responses = deepcopy(planning), deepcopy(responses)
    member = responses["participants"][0]
    planning["roster"] = [member["participant_id"]]
    # Draft status does not prevent extraction; missing required answers still produce issues.
    member["response_status"] = "complete"
    plan, reply = map_snapshots(planning, responses)
    enrichment = None
    initial_requests = set()
    if fact_enricher is not None:
        if planning.get("interpretation_policy") == "facts-v1" and planning.get("execution_mode", "options") == "options":
            initial_requests = {(r["option_id"], r["attribute_id"]) for r in requested_facts(planning, responses)}
        planning, enrichment = fact_enricher.enrich(planning, responses)
        plan, reply = map_snapshots(planning, responses)
    policy = {"group_objective": plan["group_objective"]} if plan.get("group_objective") else None
    processed = preprocess(plan, reply, policy=policy, semantic_provider=semantic_provider)
    planning, processed, enrichment = _supplement_discovered_facts(
        planning, responses, processed, enrichment,
        initial_requests=initial_requests, fact_enricher=fact_enricher,
        semantic_provider=semantic_provider, policy=policy)
    plan, reply = map_snapshots(planning, responses)
    refs = {key: planning[key] for key in ("plan_id", "round_id", "option_revision", "option_snapshot_id")}
    refs["response_snapshot_id"] = responses["snapshot_id"]
    packet = processed.get("preparation", {})
    status = packet.get("status", processed["status"])
    issues = list(processed["issues"])
    if status == "ready":
        adapted = adapt_preparation(packet, plan, responses)
        status = adapted["status"]
        issues.extend(adapted.get("issues", []))
    return {"status": status,
            **({"fact_enrichment": enrichment} if enrichment is not None else {}),
            "input_refs": refs, "member_states": {member["participant_id"]: "draft"},
            "processing": processed, "issues": issues,
            "preview_member_id": member["participant_id"], "response_revision": responses["response_revision"]}
