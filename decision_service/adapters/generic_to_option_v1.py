"""Adapt a ready generic preparation packet to ``generic-option-v1``."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from decision_service.contract import DEFAULT_OBJECTIVE
from decision_service.generic_option_contract import (
    SCHEMA_VERSION,
    SUPPORTED_HARD_RULES,
    SUPPORTED_SOFT_RULES,
    SUPPORTED_VALUE_TYPES,
    ContractError,
    validate_handoff,
)


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _result(status: str, issues: list[dict[str, str]], algorithm_input: dict | None = None) -> dict:
    return {"status": status, "issues": issues, "algorithm_input": algorithm_input}


def adapt_generic_to_option_v1(preparation: dict[str, Any]) -> dict:
    """Create a generic executable handoff for scalar option choices.

    It supports confirmed scalar facts, equality/inequality hard constraints,
    positive and avoidance preferences, numeric utilities, and indifference.
    Tag-set and scenario semantics stay in preparation until their dedicated
    matchers are implemented.
    """
    if not isinstance(preparation, dict) or preparation.get("status") != "ready":
        return _result("needs_information", [_issue("PREPARATION_NOT_READY", "Generic preparation must be ready before adaptation")])

    issues: list[dict[str, str]] = []
    questions = {item.get("question_id"): item for item in preparation.get("scoring_model", {}).get("questions", [])}
    if None in questions:
        return _result("invalid_input", [_issue("INVALID_PREPARATION", "Every question needs a question_id")])
    criteria = {item.get("attribute_id"): item for item in preparation.get("criteria", [])}

    relevant = {entry.get("attribute_id") for entry in preparation.get("constraints", []) + preparation.get("preferences", [])}
    for attribute_id in relevant:
        definition = criteria.get(attribute_id)
        if definition is None or definition.get("value_type") not in SUPPORTED_VALUE_TYPES:
            issues.append(_issue("UNSUPPORTED_VALUE_TYPE", f"{attribute_id} needs a later generic matcher rule"))
    for constraint in preparation.get("constraints", []):
        if constraint.get("kind") == "unlimited":
            continue
        if constraint.get("status") != "confirmed" or constraint.get("constraint_rule") not in SUPPORTED_HARD_RULES:
            issues.append(_issue("UNSUPPORTED_HARD_CONSTRAINT", "This hard constraint needs a later generic matcher rule"))
    for preference in preparation.get("preferences", []):
        if preference.get("kind") == "indifferent":
            continue
        definition = criteria.get(preference.get("attribute_id"), {})
        if (preference.get("polarity") == "avoid" and definition.get("value_type") in {"number", "decimal"}
                and preference.get("utility_rule") != "attribute_match_v1"):
            issues.append(_issue("UNSUPPORTED_PREFERENCE", "Numeric avoidance needs an explicit utility policy"))
        if preference.get("utility_rule") not in SUPPORTED_SOFT_RULES:
            issues.append(_issue("UNSUPPORTED_PREFERENCE", "This preference needs a later generic matcher rule"))
    preference_keys = {
        (entry.get("participant_id"), entry.get("source_question_id"), entry.get("attribute_id"))
        for entry in preparation.get("preferences", [])
    }
    weight_keys = set()
    for row in preparation.get("scoring_model", {}).get("member_weights", []):
        key = (row.get("participant_id"), row.get("source_question_id"), row.get("attribute_id"))
        if key not in preference_keys:
            continue
        if row.get("status") != "resolved" or not isinstance(row.get("effective_weight"), (int, float)):
            issues.append(_issue("UNRESOLVED_MEMBER_WEIGHTS", "Every active member preference needs a resolved effective weight"))
        else:
            weight_keys.add(key)
    if preference_keys - weight_keys:
        issues.append(_issue("MISSING_MEMBER_WEIGHTS", "Every active member preference needs an effective weight"))
    if issues:
        return _result("unsupported", issues)

    context = deepcopy(preparation.get("context", {}))
    context.update(schema_version=SCHEMA_VERSION, algorithm_version="generic-option-baseline-v1")
    handoff = {
        "context": context,
        "criteria": deepcopy(preparation.get("criteria", [])),
        "candidates": deepcopy(preparation.get("candidates", [])),
        "participants": deepcopy(preparation.get("participants", [])),
        "constraints": deepcopy(preparation.get("constraints", [])),
        "preferences": deepcopy(preparation.get("preferences", [])),
        "scoring_model": {
            "questions": [deepcopy(question) for question in questions.values() if question.get("role") in {"hard", "soft"}],
            "member_weights": deepcopy(preparation.get("scoring_model", {}).get("member_weights", [])),
            "group_objective": deepcopy(preparation.get("scoring_model", {}).get("group_objective", DEFAULT_OBJECTIVE)),
            "missing_fact_policy": "unresolved",
        },
    }
    try:
        validate_handoff(handoff)
    except ContractError as exc:
        return _result("invalid_input", [_issue("INVALID_GENERIC_OPTION_HANDOFF", str(exc))])
    return _result("ready", [], handoff)
