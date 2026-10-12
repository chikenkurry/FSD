"""Validate identities, evidence, supported rules and weights before matching."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
from typing import Any

from decision_service.contract import ContractError as ActivityContractError, group_objective


SCHEMA_VERSION = "generic-option-v1"
SUPPORTED_VALUE_TYPES = {"category", "boolean", "number", "decimal", "tag_set"}
SUPPORTED_SOFT_RULES = {
    "attribute_match_v1", "neutral_v1", "numeric_target_v1",
    "numeric_maximize_v1", "numeric_minimize_v1", "numeric_range_v1",
    "tag_overlap_v1",
}
SUPPORTED_HARD_RULES = {
    "equals_v1", "not_equals_v1", "maximum_v1", "minimum_v1",
    "less_than_v1", "greater_than_v1", "within_range_v1",
    "contains_all_v1", "excludes_all_v1",
}


class ContractError(ValueError):
    pass


def validate_handoff(handoff: dict[str, Any]) -> None:
    try:
        _validate_handoff(handoff)
    except (KeyError, TypeError, AttributeError, ValueError, InvalidOperation) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("Malformed generic handoff") from exc


def _validate_handoff(handoff: dict[str, Any]) -> None:
    if not isinstance(handoff, dict):
        raise ContractError("Handoff must be an object")
    if handoff.get("context", {}).get("schema_version") != SCHEMA_VERSION:
        raise ContractError("Unsupported generic option schema version")
    for field in ("candidates", "participants", "constraints", "preferences"):
        if not isinstance(handoff.get(field), list):
            raise ContractError(f"{field} must be a list")
    if not handoff["candidates"] or not handoff["participants"]:
        raise ContractError("At least one candidate and participant are required")
    option_ids = _unique_ids(
        handoff["candidates"], "option_id", "Candidates need unique option_id values",
    )
    participant_ids = _unique_ids(
        handoff["participants"], "participant_id", "Participants need unique participant_id values",
    )
    weights = handoff.get("scoring_model", {}).get("member_weights")
    if not isinstance(weights, list):
        raise ContractError("scoring_model.member_weights must be a list")
    required = {p["participant_id"] for p in handoff["participants"] if p.get("is_required_for_decision", True)}
    if not required:
        raise ContractError("At least one required participant is needed")
    definitions = _criterion_definitions(handoff.get("criteria", []))
    questions = {q["question_id"] for q in handoff["scoring_model"]["questions"]}
    _validate_objective(handoff["scoring_model"])
    _validate_facts(handoff["candidates"], definitions)
    _validate_participants(handoff["participants"])
    _validate_answer_references(
        handoff["constraints"] + handoff["preferences"], participant_ids, questions, definitions,
    )
    _validate_constraints(handoff["constraints"], definitions)
    _validate_preferences(handoff["preferences"], definitions)
    _validate_member_weights(weights, handoff["preferences"])
    _validate_option_flags(
        handoff.get("option_flags", []), handoff["candidates"], option_ids, participant_ids,
    )


def _unique_ids(records: list[dict], field: str, message: str) -> list[str]:
    ids = [record.get(field) for record in records]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise ContractError(message)
    return ids


def _criterion_definitions(criteria: list[dict]) -> dict:
    if not isinstance(criteria, list):
        raise ContractError("criteria must be a list")
    definitions = {c["attribute_id"]: c for c in criteria}
    if len(definitions) != len(criteria) or any(not isinstance(aid, str) or not aid for aid in definitions):
        raise ContractError("Criteria need unique attribute IDs")
    return definitions


def _validate_objective(model: dict) -> None:
    try:
        objective = group_objective(model.get("group_objective"))
    except ActivityContractError as exc:
        raise ContractError(str(exc)) from exc
    if model.get("group_objective") != objective:
        raise ContractError("Group objective must specify all policy fields")


def _validate_facts(candidates: list[dict], definitions: dict) -> None:
    for candidate in candidates:
        seen = set()
        for fact in candidate.get("facts", []):
            aid = fact["attribute_id"]
            if aid in seen or aid not in definitions or fact.get("status") not in {"confirmed", "estimated", "unknown"}:
                raise ContractError("Invalid or duplicate option fact")
            seen.add(aid)
            definition = definitions[aid]
            if fact.get("value_type", definition["value_type"]) != definition["value_type"]:
                raise ContractError("Fact type differs from its criterion")
            if fact.get("unit", definition.get("unit")) != definition.get("unit"):
                raise ContractError("Fact unit differs from its criterion")
            if fact.get("status") != "unknown":
                _validate_value(fact.get("value"), definitions[aid]["value_type"])


def _validate_participants(participants: list[dict]) -> None:
    for participant in participants:
        if participant.get("response_status", "complete") not in {"complete", "incomplete", "stale", "needs_clarification"}:
            raise ContractError("Invalid member response status")


def _validate_answer_references(
    records: list[dict], participant_ids: list[str], questions: set[str], definitions: dict,
) -> None:
    for record in records:
        if record["participant_id"] not in participant_ids or record.get("source_question_id") not in questions:
            raise ContractError("Unknown member or source question")
        if record["attribute_id"] not in definitions:
            raise ContractError("Unknown criterion")
        if record.get("scope", "all") != "all":
            raise ContractError("Scoped preferences require an explicit matcher policy")


def _validate_constraints(constraints: list[dict], definitions: dict) -> None:
    for constraint in constraints:
        if constraint.get("kind") == "unlimited":
            continue
        if constraint.get("status") != "confirmed" or constraint.get("constraint_rule") not in SUPPORTED_HARD_RULES:
            raise ContractError("Hard requirements must be confirmed and supported")
        rule, value = constraint["constraint_rule"], constraint.get("required_value")
        kind = definitions[constraint["attribute_id"]]["value_type"]
        if rule in {"maximum_v1", "minimum_v1", "less_than_v1", "greater_than_v1", "within_range_v1"} and kind not in {"number", "decimal"}:
            raise ContractError("Numeric requirements need a numeric criterion")
        if rule in {"contains_all_v1", "excludes_all_v1"} and kind != "tag_set":
            raise ContractError("Tag requirements need a tag-set criterion")
        if rule in {"maximum_v1", "minimum_v1", "less_than_v1", "greater_than_v1"}:
            _number(value)
        elif rule == "within_range_v1":
            _bounds(value)
        else:
            _validate_value(value, definitions[constraint["attribute_id"]]["value_type"])


def _validate_preferences(preferences: list[dict], definitions: dict) -> None:
    for preference in preferences:
        rule = preference.get("utility_rule")
        if rule not in SUPPORTED_SOFT_RULES or preference.get("polarity", "prefer") not in {"prefer", "avoid"}:
            raise ContractError("Unsupported preference")
        params = preference.get("utility_parameters", {})
        kind = definitions[preference["attribute_id"]]["value_type"]
        if rule.startswith("numeric_") and (kind not in {"number", "decimal"} or preference.get("polarity", "prefer") != "prefer"):
            raise ContractError("Numeric utility needs a numeric criterion and supported polarity")
        if rule == "tag_overlap_v1" and kind != "tag_set":
            raise ContractError("Tag overlap needs a tag-set criterion")
        if rule in {"attribute_match_v1", "tag_overlap_v1"}:
            _validate_value(preference.get("preferred_value"), kind)
        if rule == "numeric_target_v1" and _number(params.get("scale")) <= 0:
            raise ContractError("Numeric targets need a positive scale")
        if rule == "numeric_target_v1":
            _number(preference.get("preferred_value"))
        if rule in {"numeric_maximize_v1", "numeric_minimize_v1"} and _number(params.get("lower_bound")) > _number(params.get("upper_bound")):
            raise ContractError("Invalid numeric domain")
        if rule == "numeric_range_v1":
            _bounds(preference.get("preferred_value"))
            if params.get("lower_bound") is not None or params.get("upper_bound") is not None:
                if _number(params.get("lower_bound")) > _number(params.get("upper_bound")):
                    raise ContractError("Invalid numeric domain")
        if rule == "neutral_v1" and preference.get("kind") != "indifferent":
            raise ContractError("Neutral utility requires explicit indifference")


def _validate_member_weights(weights: list[dict], preferences: list[dict]) -> None:
    active = {(p["participant_id"], p["source_question_id"], p["attribute_id"]) for p in preferences}
    seen = set()
    sums = {}
    for weight in weights:
        key = (weight["participant_id"], weight["source_question_id"], weight["attribute_id"])
        value = weight.get("effective_weight")
        if key in seen or key not in active or weight.get("status") != "resolved" or type(value) not in {int, float} or not math.isfinite(value) or value < 0:
            raise ContractError("Invalid member weight")
        seen.add(key)
        sums[key[0]] = sums.get(key[0], 0) + value
    if seen != active or any(not math.isclose(value, 1, abs_tol=1e-8) for value in sums.values()):
        raise ContractError("Member weights must cover preferences and sum to one")


def _validate_option_flags(
    flags: list[dict], candidates: list[dict], option_ids: list[str], participant_ids: list[str],
) -> None:
    source_options = set(option_ids) | {c["source_option_id"] for c in candidates if isinstance(c.get("source_option_id"), str)}
    for flag in flags:
        if flag["participant_id"] not in participant_ids or flag["activity_id"] not in source_options or flag["flag"] not in {"cannot_join", "needs_information"}:
            raise ContractError("Invalid option flag")


def _number(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ContractError("Expected finite numeric value")
    numeric = Decimal(str(value))
    if not numeric.is_finite():
        raise ContractError("Expected finite numeric value")
    return numeric


def _bounds(value: object) -> None:
    if not isinstance(value, dict) or value.get("lower") is None and value.get("upper") is None:
        raise ContractError("Expected bounded interval")
    lower = _number(value["lower"]) if value.get("lower") is not None else None
    upper = _number(value["upper"]) if value.get("upper") is not None else None
    if lower is not None and upper is not None and (lower > upper or lower == upper and
            not (value.get("lower_inclusive", True) and value.get("upper_inclusive", True))):
        raise ContractError("Empty interval")


def _validate_value(value: object, kind: str) -> None:
    if kind in {"number", "decimal"}:
        _number(value)
    elif kind == "boolean" and type(value) is not bool:
        raise ContractError("Expected a boolean fact")
    elif kind == "category" and not isinstance(value, str):
        raise ContractError("Expected a category fact")
    elif kind == "tag_set" and (not isinstance(value, list) or any(not isinstance(v, str) for v in value)):
        raise ContractError("Expected tag-set fact")
    elif kind not in SUPPORTED_VALUE_TYPES:
        raise ContractError("Unsupported fact type")
