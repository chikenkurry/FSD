"""Adapt a compatible generic preparation packet to the activity-v2 contract.

The generic processor intentionally has no authority to invent event times.
Callers therefore supply an execution context containing concrete candidates and
member availability intervals collected by a scheduling source.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
import math

from decision_service.contract import (
    DEFAULT_OBJECTIVE,
    MISSING_VALUE_POLICY,
    SCHEMA_VERSION,
    ContractError,
    ranking_order,
    validate_handoff,
)


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _result(status: str, issues: list[dict[str, str]], algorithm_input: dict | None = None) -> dict:
    return {"status": status, "issues": issues, "algorithm_input": algorithm_input}


def adapt_generic_to_activity_v2(preparation: dict[str, Any], execution_context: dict[str, Any]) -> dict:
    """Return an activity-v2 handoff when generic data is representable safely.

    ``execution_context`` must supply concrete candidates with ``option_id``,
    ``candidate_id``, ``activity_id``, ``start_at``, ``end_at``, and ``currency``;
    it must also supply ``availability_by_participant`` as normalized timestamp
    intervals. The adapter only supports equality-based generic preferences and
    confirmed equality hard requirements, because those are the utilities the
    activity algorithm currently implements. Integer maximum budgets are also
    supported; other numeric requirements require the generic matcher.
    """
    if not isinstance(preparation, dict) or preparation.get("status") != "ready":
        return _result("needs_information", [_issue("PREPARATION_NOT_READY", "Generic preparation must be ready before adaptation")])
    if not isinstance(execution_context, dict):
        return _result("invalid_input", [_issue("INVALID_EXECUTION_CONTEXT", "Execution context must be an object")])

    candidates = execution_context.get("candidates")
    availability = execution_context.get("availability_by_participant")
    if not isinstance(candidates, list) or not candidates:
        return _result("needs_information", [_issue("CONCRETE_CANDIDATES_REQUIRED", "Provide concrete activity/time candidates")])
    if not isinstance(availability, dict):
        return _result("needs_information", [_issue("AVAILABILITY_INTERVALS_REQUIRED", "Provide normalized availability intervals for every participant")])

    issues: list[dict[str, str]] = []
    source_candidates = {item.get("option_id"): item for item in preparation.get("candidates", [])}
    prepared_participants = preparation.get("participants", [])
    participant_ids = {item.get("participant_id") for item in prepared_participants}
    if not participant_ids or None in participant_ids:
        return _result("invalid_input", [_issue("INVALID_PREPARATION", "Preparation has no valid participants")])
    if set(availability) != participant_ids:
        return _result("needs_information", [_issue("AVAILABILITY_INTERVALS_REQUIRED", "Availability intervals must cover the preparation roster exactly")])

    execution_candidates = []
    activity_ids: list[str] = []
    covered_options = set()
    for raw in candidates:
        if not isinstance(raw, dict) or raw.get("option_id") not in source_candidates:
            issues.append(_issue("UNKNOWN_EXECUTION_OPTION", "A concrete candidate must reference a prepared option"))
            continue
        required = ("candidate_id", "activity_id", "start_at", "end_at", "currency")
        if any(not isinstance(raw.get(key), str) or not raw[key] for key in required):
            issues.append(_issue("INVALID_EXECUTION_CANDIDATE", "Concrete candidates need IDs, timestamps, and currency"))
            continue
        option = source_candidates[raw["option_id"]]
        facts = deepcopy(option.get("facts", []))
        cost = next((fact for fact in facts if fact.get("attribute_id") == "estimated_cost"), None)
        if cost is None:
            issues.append(_issue("MISSING_COST_FACT", "Each executable option needs an estimated_cost fact"))
            continue
        execution_candidates.append({
            "candidate_id": raw["candidate_id"],
            "activity_id": raw["activity_id"],
            "start_at": raw["start_at"],
            "end_at": raw["end_at"],
            "currency": raw["currency"],
            "estimated_cost_minor": cost.get("value"),
            "facts": facts,
            **({"scenario_id": raw["scenario_id"]} if isinstance(raw.get("scenario_id"), str) else {}),
        })
        covered_options.add(raw["option_id"])
        if raw["activity_id"] not in activity_ids:
            activity_ids.append(raw["activity_id"])
    if set(source_candidates) - covered_options:
        issues.append(_issue("MISSING_EXECUTION_OPTION", "Provide at least one concrete candidate for every prepared option"))
    if issues:
        return _result("needs_information", issues)

    questions = []
    for question in preparation.get("scoring_model", {}).get("questions", []):
        role = question.get("role")
        if role in {"informational", "importance"}:
            continue
        if role == "hard":
            questions.append({
                "question_id": question["question_id"], "weight": None,
                "utility_rule": None, "aggregation": "direct",
                "missing_value_policy": None, "is_hard_constraint": True,
                "criteria": question.get("criteria", [question.get("criterion")]),
            })
            continue
        if question.get("utility_rule") not in {"rating_v1", "attribute_match_v1", "neutral_v1"}:
            issues.append(_issue("UNSUPPORTED_UTILITY_RULE", "Generic utility rules need the generic-option algorithm"))
            continue
        if question.get("weight") is None:
            issues.append(_issue("UNRESOLVED_SOFT_WEIGHT", "Every executable soft question needs a normalized weight"))
            continue
        questions.append({
            "question_id": question["question_id"], "weight": question["weight"],
            "utility_rule": question["utility_rule"], "aggregation": question.get("aggregation", "direct"),
            "missing_value_policy": "unresolved", "is_hard_constraint": False,
            "criteria": question.get("criteria", [question.get("criterion")]),
        })
    if issues:
        return _result("unsupported", issues)

    # The activity scorer uses global question weights. Reject personal weight
    # changes rather than silently discarding the generic processor's policy.
    question_weights = {q["question_id"]: q["weight"] for q in questions if not q["is_hard_constraint"]}
    for row in preparation.get("scoring_model", {}).get("member_weights", []):
        qid, pid = row.get("source_question_id"), row.get("participant_id")
        criteria = {p.get("attribute_id") for p in preparation.get("preferences", [])
                    if p.get("source_question_id") == qid and p.get("participant_id") == pid}
        expected = question_weights.get(qid, 0) / len(criteria) if criteria else 0
        if row.get("status") != "resolved" or not isinstance(row.get("effective_weight"), (int, float)) or not math.isclose(row["effective_weight"], expected, abs_tol=1e-9):
            return _result("unsupported", [_issue("UNSUPPORTED_MEMBER_WEIGHTS", "The activity scorer cannot represent these member importance weights")])

    preferences = []
    for preference in preparation.get("preferences", []):
        if preference.get("polarity", "prefer") != "prefer" or preference.get("scope", "all") != "all":
            issues.append(_issue("UNSUPPORTED_PREFERENCE", "Avoidance and scoped generic preferences need the generic-option algorithm"))
            continue
        if preference.get("kind") not in {"rating", "attribute_preference", "indifferent"}:
            issues.append(_issue("UNSUPPORTED_PREFERENCE", "Unsupported generic preference kind"))
            continue
        preferences.append(deepcopy(preference))

    constraints_by_member = {participant_id: {
        "participant_id": participant_id,
        "availability": {"available_intervals": deepcopy(availability[participant_id])},
        "budget": {"kind": "unlimited"},
        "required_attributes": [],
        "candidate_flags": [],
        "answer_sources": [],
    } for participant_id in participant_ids}
    for constraint in preparation.get("constraints", []):
        participant_id = constraint.get("participant_id")
        if participant_id not in constraints_by_member:
            issues.append(_issue("INVALID_CONSTRAINT_PARTICIPANT", "Constraint references an unknown participant"))
            continue
        attribute_id = constraint.get("attribute_id")
        if attribute_id == "availability":
            issues.append(_issue("UNSUPPORTED_AVAILABILITY", "Generic date availability cannot be replaced by timestamp intervals"))
            continue
        if attribute_id == "max_cost":
            if constraint.get("kind") == "unlimited":
                continue
            if constraint.get("status") != "confirmed" or constraint.get("constraint_rule") != "maximum_v1" or type(constraint.get("required_value")) is not int:
                issues.append(_issue("UNSUPPORTED_BUDGET_RULE", "Only confirmed integer maximum budgets are activity-v2 compatible"))
                continue
            previous = constraints_by_member[participant_id]["budget"].get("max_cost_minor")
            bound = constraint["required_value"] if previous is None else min(previous, constraint["required_value"])
            constraints_by_member[participant_id]["budget"] = {
                "kind": "limited", "max_cost_minor": bound,
                "currency": execution_candidates[0]["currency"],
            }
            if constraint.get("source_answer_id"):
                constraints_by_member[participant_id]["answer_sources"].append(deepcopy(constraint))
            continue
        if constraint.get("constraint_rule") != "equals_v1" or constraint.get("status") != "confirmed":
            issues.append(_issue("UNSUPPORTED_HARD_CONSTRAINT", "Only confirmed equality requirements are activity-v2 compatible"))
            continue
        constraints_by_member[participant_id]["required_attributes"].append(deepcopy(constraint))
    if issues:
        return _result("unsupported", issues)

    objective = deepcopy(preparation.get("scoring_model", {}).get("group_objective", DEFAULT_OBJECTIVE))
    context = deepcopy(preparation.get("context", {}))
    context.update({
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": "baseline-v2",
        "activity_ids": activity_ids,
    })
    handoff = {
        "context": context,
        "criteria": deepcopy(preparation.get("criteria", [])),
        "candidates": execution_candidates,
        "participants": deepcopy(prepared_participants),
        "constraints": list(constraints_by_member.values()),
        "preferences": preferences,
        "scoring_model": {
            "questions": questions,
            "group_objective": objective,
            "ranking_policy": {"feasibility_policy": "all_required_participants", "sort_order": ranking_order(objective)},
            "missing_value_policy": deepcopy(MISSING_VALUE_POLICY),
        },
    }
    try:
        validate_handoff(handoff)
    except ContractError as exc:
        return _result("invalid_input", [_issue("INVALID_ACTIVITY_V2_HANDOFF", str(exc))])
    return _result("ready", [], handoff)
