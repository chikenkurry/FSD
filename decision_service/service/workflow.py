"""Validate frozen inputs and preprocess them before invoking a supported matcher."""
from copy import deepcopy
from decision_service.preprocessing import preprocess

from .enrichment import requested_facts
from .execution import execute_preparation, adapt_preparation
from .date_poll import date_poll_summary
from .snapshots import map_snapshots
from decision_service.preprocessing.common import InputError
from .views import member_review, public_result


def _processing_policy(plan: dict) -> dict | None:
    """Pass only supported, versioned processing controls to preprocessing."""
    policy = {}
    if plan.get("group_objective"):
        policy["group_objective"] = plan["group_objective"]
    if plan.get("weighting_policy_version") is not None:
        policy["weighting_policy_version"] = plan["weighting_policy_version"]
    return policy or None


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
    run = _execute(planning, responses, semantic_provider=semantic_provider, fact_enricher=fact_enricher)
    poll = date_poll_summary(planning.get("questions", []), responses.get("participants", []))
    return {**run, "date_poll": poll} if poll else run


def _execute(planning: dict, responses: dict, *, semantic_provider=None, fact_enricher=None) -> dict:
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
    policy = _processing_policy(plan)
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
    if packet and packet["status"] == "needs_information":
        ranked = _rank_options_with_facts(planning, responses, processed, base, plan)
        if ranked:
            return ranked
    if not packet or packet["status"] != "ready":
        return {**base, "status": packet["status"] if packet else processed["status"], "issues": processed["issues"]}
    return {**base, **execute_preparation(packet, plan, responses)}


def _rank_options_with_facts(planning, responses, processed, base, plan):
    """Rank the options whose facts are complete when the only gap is facts on other options.

    Options still missing facts after the evidence check are listed as unresolved instead of
    blocking the whole result. The prepared answers are reused, so no model call is repeated.
    Returns None when anything else needs attention.
    """
    packet = processed["preparation"]
    missing = {r["option_id"] for r in packet.get("fact_requests", [])}
    blocking = [i for i in processed["issues"] if i["code"] not in {"MISSING_OPTION_FACTS", "EXECUTION_ADAPTER_REQUIRED"}]
    complete = [c for c in packet["candidates"] if c["option_id"] not in missing]
    if not missing or blocking or len(complete) < 2 or planning.get("execution_mode", "options") != "options":
        return None
    trimmed = {**deepcopy(packet), "candidates": deepcopy(complete), "fact_requests": [], "status": "ready"}
    try:
        run = execute_preparation(trimmed, plan, responses)
    except InputError:
        return None
    if run.get("status") != "ranked":
        return None
    run["result"]["candidate_results"] = [*run["result"].get("candidate_results", []), *(
        {"option_id": o["option_id"], "feasibility": "unresolved", "explanation_codes": ["MISSING_OPTION_FACT"]}
        for o in planning["options"] if o["option_id"] in missing)]
    excluded = [{"option_id": o["option_id"], "title": o.get("title", ""),
                 "missing": sorted({r["attribute_id"] for r in packet["fact_requests"] if r["option_id"] == o["option_id"]})}
                for o in planning["options"] if o["option_id"] in missing]
    retried = {**processed, "status": "ready", "preparation": trimmed,
               "issues": [i for i in processed["issues"] if i["code"] != "MISSING_OPTION_FACTS"]}
    return {**base, "processing": retried, "excluded_options": excluded, **run}


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
    policy = _processing_policy(plan)
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
