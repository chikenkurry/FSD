"""Adapt prepared preferences and Participation constraints for each executor."""
from copy import deepcopy

from decision_service.adapters import (
    adapt_generic_to_activity_v2,
    adapt_generic_to_option_v1,
    adapt_scenarios_to_option_v1,
)
from decision_service.algorithm import run_decision as run_activity
from decision_service.generic_algorithm import run_decision as run_options
from decision_service.preprocessing.money import minor_amount


def execute_preparation(packet: dict, plan: dict, responses: dict) -> dict:
    mode = plan.get("execution_mode", "options")
    constraint_rows = {row["participant_id"]: row for row in responses.get("constraints", [])}
    if mode == "scheduled":
        adapted = _adapt_scheduled(packet, plan, constraint_rows, responses["snapshot_id"])
    elif mode == "scenarios":
        adapted = adapt_scenarios_to_option_v1(packet)
    else:
        adapted = adapt_generic_to_option_v1(packet)
    if adapted["status"] != "ready":
        return {"status": adapted["status"], "issues": adapted["issues"]}

    handoff = adapted["algorithm_input"]
    if mode == "scheduled":
        result = run_activity(handoff).as_dict()
    else:
        handoff["option_flags"] = [
            {"participant_id": pid, **flag}
            for pid, row in constraint_rows.items()
            for flag in row.get("activity_flags", [])
        ]
        result = run_options(handoff).as_dict()
    return {
        "status": result["status"], "result": result, "algorithm_input": handoff,
        "issues": [{"code": code} for code in result.get("issues", [])],
    }


def _adapt_scheduled(packet: dict, plan: dict, constraint_rows: dict, snapshot_id: str) -> dict:
    if any(c["attribute_id"] == "availability" for c in packet["constraints"]):
        return {"status": "unsupported", "issues": [{"code": "TIMESTAMP_AVAILABILITY_REQUIRED"}]}
    prepared = _convert_scheduled_costs(packet, plan["currency"], plan.get("currency_minor_digits", 2))
    context = deepcopy(plan.get("execution_context", {}))
    context["availability_by_participant"] = {pid: row.get("availability", {}).get("available_intervals", []) for pid, row in constraint_rows.items()}
    adapted = adapt_generic_to_activity_v2(prepared, context)
    if adapted["status"] == "ready":
        _apply_scheduled_flags(adapted["algorithm_input"], constraint_rows, snapshot_id)
    return adapted


def _convert_scheduled_costs(packet: dict, currency: str, digits: int) -> dict:
    prepared = deepcopy(packet)
    # The activity contract uses integer minor units, unlike generic option facts.
    for candidate in prepared["candidates"]:
        for fact in candidate["facts"]:
            if fact["attribute_id"] == "max_cost":
                fact.update(attribute_id="estimated_cost", value_type="integer", unit=f"{currency}_minor",
                            value=minor_amount(fact["value"], digits, "candidate.cost") if fact["value"] is not None else None)
    for criterion in prepared["criteria"]:
        if criterion["attribute_id"] == "max_cost":
            criterion.update(value_type="integer", unit=f"{currency}_minor")
    prepared["criteria"].append({"attribute_id": "estimated_cost", "value_type": "integer", "unit": f"{currency}_minor"})
    for constraint in prepared["constraints"]:
        if constraint["attribute_id"] == "max_cost" and constraint.get("kind") != "unlimited":
            constraint["required_value"] = minor_amount(constraint["required_value"], digits, "member.budget")
            constraint.update(value_type="integer", unit=f"{currency}_minor")
    return prepared


def _apply_scheduled_flags(handoff: dict, constraint_rows: dict, snapshot_id: str) -> None:
    flag_question = "__participation_activity_flags"
    if any(row.get("activity_flags") for row in constraint_rows.values()):
        handoff["scoring_model"]["questions"].append({"question_id": flag_question, "weight": None,
            "utility_rule": None, "aggregation": "direct", "missing_value_policy": None,
            "is_hard_constraint": True, "criteria": []})
    for constraint in handoff["constraints"]:
        flags = constraint_rows.get(constraint["participant_id"], {}).get("activity_flags", [])
        constraint["candidate_flags"] = [{"candidate_id": c["candidate_id"], "flag": flag["flag"],
            "source_question_id": flag_question, "source_type": "member_response", "evidence": flag["flag"],
            "source_answer_id": f"{snapshot_id}:{constraint['participant_id']}:{flag['activity_id']}"}
            for flag in flags for c in handoff["candidates"] if c["activity_id"] == flag["activity_id"]]
