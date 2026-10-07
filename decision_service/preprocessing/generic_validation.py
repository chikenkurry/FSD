"""Validate generic comparison declarations and member weights before export."""

from __future__ import annotations

import math
from decimal import Decimal

from .common import InputError, require_object
from .generic_mapping import HARD_RULES, NUMERIC_SOFT_RULES, SOFT_RULES, typed_value
from .generic_values import numeric_semantics

def validate_preparation(handoff: dict) -> None:
    """Reject invalid references and declarations before exporting preparation."""
    require_object(handoff, "preparation")
    registry = {entry["attribute_id"]: entry for entry in handoff["criteria"]}
    participants = {p["participant_id"] for p in handoff["participants"]}
    questions = {q["question_id"]: q for q in handoff["scoring_model"]["questions"]}
    for question in questions.values():
        mapping = question["mapping"]
        if mapping["status"] != "resolved":
            continue
        if mapping["attribute_id"] not in registry or registry[mapping["attribute_id"]]["unit"] != mapping["unit"]:
            raise InputError("INVALID_PREPARATION", "preparation.questions", "Question mapping has an unknown criterion or unit")
        if question["role"] == "soft":
            allowed = NUMERIC_SOFT_RULES if mapping["value_type"] in {"number", "decimal"} else {SOFT_RULES.get(mapping["value_type"])}
        else:
            allowed = HARD_RULES[mapping["value_type"]]
        if mapping["comparison_rule"] not in allowed:
            raise InputError("UNSUPPORTED_UTILITY_RULE", "preparation.questions", "Comparison does not support the question type")
    seen_requirements = {}
    for collection in (handoff["preferences"], handoff["constraints"]):
        seen = set()
        for entry in collection:
            key = (entry["participant_id"], entry["source_question_id"], entry["attribute_id"], entry.get("polarity", "prefer"))
            if key in seen or key[0] not in participants or key[1] not in questions or key[2] not in registry:
                raise InputError("INVALID_PREPARATION", "preparation", "Duplicate or unknown normalized answer reference")
            seen.add(key)
            if not entry["source_answer_id"] or not entry["evidence"]:
                raise InputError("INVALID_PREPARATION", "preparation", "Normalized answer needs provenance")
            definition = registry[key[2]]
            if entry.get("unit") != definition["unit"]:
                raise InputError("UNIT_MISMATCH", "preparation", "Answer unit differs from its criterion")
            _validate_comparison(entry, definition)
            if "required_value" in entry and entry["confirmation_status"] == "confirmed":
                conflict_key = (entry["participant_id"], entry["attribute_id"], entry["constraint_rule"])
                if conflict_key in seen_requirements and seen_requirements[conflict_key] != entry["required_value"]:
                    raise InputError("CONFLICTING_ANSWER", "preparation.constraints", "Confirmed answers give different limits for the same criterion")
                seen_requirements[conflict_key] = entry["required_value"]
    _validate_member_weights(handoff, participants, questions)
    _validate_numeric_requirements(handoff["constraints"], registry)


def _validate_comparison(entry: dict, definition: dict) -> None:
    kind = definition["value_type"]
    hard = "required_value" in entry
    rule = entry.get("constraint_rule" if hard else "utility_rule")
    if entry["kind"] in {"indifferent", "unlimited"}:
        return
    if hard:
        allowed = HARD_RULES[kind] | ({"excludes_all_v1"} if kind == "tag_set" else {"not_equals_v1"} if kind in {"boolean", "category"} else set())
    else:
        allowed = NUMERIC_SOFT_RULES if kind in {"number", "decimal"} else {SOFT_RULES.get(kind)}
    if rule not in allowed:
        raise InputError("UNSUPPORTED_UTILITY_RULE", "preparation", "Answer comparison does not support its criterion type")
    value = entry["required_value" if hard else "preferred_value"]
    if rule in {"numeric_maximize_v1", "numeric_minimize_v1"}:
        parameters = entry["utility_parameters"]
        lower, upper = parameters.get("lower_bound"), parameters.get("upper_bound")
        if value is not None or (lower is None) != (upper is None):
            raise InputError("INVALID_PREPARATION", "preparation.preferences", "Directional preferences need a null target and paired domain bounds")
        if lower is not None:
            typed_value(lower, kind, "preparation.preferences")
            typed_value(upper, kind, "preparation.preferences")
            if Decimal(str(lower)) > Decimal(str(upper)):
                raise InputError("INVALID_PREPARATION", "preparation.preferences", "Numeric domain bounds are reversed")
    elif rule in {"numeric_range_v1", "within_range_v1"}:
        numeric_semantics(value, definition, "preparation", "range")
    elif kind != "date_intervals":
        typed_value(value, kind, "preparation")
    if rule == "numeric_target_v1":
        scale = entry["utility_parameters"].get("scale")
        if type(scale) not in {int, float} or not 0 < scale <= 1e308:
            raise InputError("INVALID_PREPARATION", "preparation.preferences", "Numeric target needs a positive finite scale")


def _validate_member_weights(handoff: dict, participants: set, questions: dict) -> None:
    active = {(p["participant_id"], p["source_question_id"], p["attribute_id"])
              for p in handoff["preferences"] if questions[p["source_question_id"]]["weight"]}
    seen, totals = set(), {}
    for row in handoff["scoring_model"]["member_weights"]:
        key = (row["participant_id"], row["source_question_id"], row["attribute_id"])
        if key not in active or key in seen:
            raise InputError("INVALID_PREPARATION", "preparation.member_weights", "Weight references an unknown or repeated soft criterion")
        seen.add(key)
        for field in ("base_weight", "importance_multiplier"):
            value = row[field]
            if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
                raise InputError("INVALID_PREPARATION", "preparation.member_weights", "Weights must be finite and nonnegative")
        if row["status"] == "unresolved":
            if row["effective_weight"] is not None:
                raise InputError("INVALID_PREPARATION", "preparation.member_weights", "Unresolved weights cannot be used for scoring")
            continue
        value = row["effective_weight"]
        if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1:
            raise InputError("INVALID_PREPARATION", "preparation.member_weights", "Effective weights must be finite fractions")
        totals[key[0]] = totals.get(key[0], 0) + value
    if seen != active or any(not math.isclose(value, 1, abs_tol=1e-9) for value in totals.values()):
        raise InputError("INVALID_PREPARATION", "preparation.member_weights", "Each member's active weights must be present and normalized")
    for entry in handoff["importance"]:
        if entry["participant_id"] not in participants or entry["source_question_id"] is not None and entry["source_question_id"] not in questions:
            raise InputError("INVALID_PREPARATION", "preparation.importance", "Importance has an unknown member or question")
        if not entry["source_answer_id"] or not entry["evidence"]:
            raise InputError("INVALID_PREPARATION", "preparation.importance", "Importance needs answer provenance")


def _validate_numeric_requirements(constraints: list[dict], registry: dict) -> None:
    bounds = {}
    for entry in constraints:
        if "required_value" not in entry or entry["confirmation_status"] != "confirmed" or registry[entry["attribute_id"]]["value_type"] not in {"number", "decimal"}:
            continue
        rule, value = entry["constraint_rule"], entry["required_value"]
        interval = {"lower": None, "upper": None, "lower_inclusive": True, "upper_inclusive": True}
        if rule == "within_range_v1":
            interval = value
        elif rule in {"minimum_v1", "greater_than_v1", "equals_v1"}:
            interval.update(lower=value, lower_inclusive=rule != "greater_than_v1")
        if rule in {"maximum_v1", "less_than_v1", "equals_v1"}:
            interval.update(upper=value, upper_inclusive=rule != "less_than_v1")
        key = (entry["participant_id"], entry["attribute_id"])
        combined = bounds.setdefault(key, {"lower": None, "upper": None, "lower_inclusive": True, "upper_inclusive": True})
        for endpoint in ("lower", "upper"):
            if interval[endpoint] is None:
                continue
            candidate = Decimal(str(interval[endpoint]))
            current = combined[endpoint]
            tighter = current is None or (candidate > current if endpoint == "lower" else candidate < current)
            inclusive = endpoint + "_inclusive"
            if tighter:
                combined.update({endpoint: candidate, inclusive: interval[inclusive]})
            elif candidate == current:
                combined[inclusive] = combined[inclusive] and interval[inclusive]
        lower, upper = combined["lower"], combined["upper"]
        if lower is not None and upper is not None and (lower > upper or lower == upper and not (combined["lower_inclusive"] and combined["upper_inclusive"])):
            raise InputError("CONFLICTING_ANSWER", "preparation.constraints", "Confirmed numeric requirements have no overlapping values")
