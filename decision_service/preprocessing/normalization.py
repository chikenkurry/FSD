"""Convert extracted answers and frozen option facts into execution values."""

from __future__ import annotations

import json

from decision_service.contract import ContractError, validate_value

from .common import InputError, require_object, require_text


def provenance(answer: dict, source_type: str = "member_response", evidence: str | None = None) -> dict:
    value = answer.get("value")
    return {
        "source_question_id": answer["question_id"],
        "source_answer_id": answer["answer_id"],
        "source_type": source_type,
        "evidence": evidence if evidence is not None else value if isinstance(value, str) else json.dumps(value, sort_keys=True),
    }


def preference_metadata(preference: dict, answer: dict) -> dict:
    indifferent = preference["kind"] == "indifferent"
    return {
        **preference,
        **provenance(answer),
        "scope": "activity" if "activity_id" in preference else "all",
        "utility_rule": preference.get("utility_rule", "rating_v1"),
        "status": "explicitly_indifferent" if indifferent else "confirmed",
    }


def requirement_metadata(requirement: dict, member_id: str, answer: dict) -> dict:
    return {**requirement, **provenance(answer), "participant_id": member_id,
            "confirmation_status": "confirmed", "status": "confirmed"}


def semantic_binding(raw: object, path: str) -> dict | None:
    if raw is None:
        return None
    binding = require_object(raw, path)
    attribute_id = require_text(binding.get("attribute_id"), f"{path}.attribute_id")
    if attribute_id == "estimated_cost":
        raise InputError("UNSUPPORTED_CRITERION", path, "Use a budget question for cost constraints")
    definition = {"attribute_id": attribute_id, "value_type": binding.get("value_type", "category"),
                  "unit": binding.get("unit")}
    values = require_object(binding.get("values"), f"{path}.values")
    if not values:
        raise InputError("MISSING_MAPPING", path, "Provide semantic values mapped to typed attribute values")
    for label, value in values.items():
        require_text(label, f"{path}.values")
        try:
            if value is not None:
                validate_value(value, definition, path)
        except ContractError as exc:
            raise InputError("INVALID_MAPPING", path, str(exc)) from exc
    return {**definition, "values": values}


def normalize_semantic(question: dict, interpretation: dict, member_id: str, answer: dict) -> tuple[dict | None, dict | None]:
    """Return (preference, requirement); unmapped meanings need clarification.

    Confirmation must echo the mapped attribute and value from a reviewed
    interpretation. A generic flag on an answer cannot confirm a new meaning.
    """
    path = f"responses.participants.{member_id}.answers.{question['question_id']}"
    binding = question["semantic_binding"]
    if binding is None or interpretation["value"] not in binding["values"]:
        raise InputError("UNMAPPED_SEMANTIC_VALUE", path, "Map this meaning to a supported attribute before execution")
    value = binding["values"][interpretation["value"]]
    metadata = {"participant_id": member_id,
                **provenance(answer, "semantic_model", interpretation["evidence"])}
    if question["kind"] == "semantic_requirement":
        confirmation = answer.get("confirmed_requirement")
        expected = {"attribute_id": binding["attribute_id"], "required_value": value}
        if binding["unit"] is not None:
            expected["unit"] = binding["unit"]
        if isinstance(confirmation, dict) and value is not None:
            try:
                validate_value(confirmation.get("required_value"), binding, path)
            except ContractError as exc:
                raise InputError("CONFIRM_REQUIREMENT", path, str(exc)) from exc
        if confirmation != expected:
            raise InputError("CONFIRM_REQUIREMENT", path, "Confirm the interpreted attribute and required value")
        if value is None:
            return None, None
        return None, {**metadata, **expected, "confirmation_status": "confirmed", "status": "confirmed"}
    if value is None:
        return {**metadata, "kind": "indifferent", "scope": "all", "utility_rule": "neutral_v1",
                "status": "explicitly_indifferent"}, None
    return {**metadata, "kind": "attribute_preference", "attribute_id": binding["attribute_id"],
            "preferred_value": value, "scope": "all", "utility_rule": "attribute_match_v1", "status": "estimated"}, None


def execution_candidates(candidates: list[dict], questions: list[dict]) -> tuple[list[dict], list[dict]]:
    definitions = {}

    def register(definition: dict) -> None:
        aid = definition["attribute_id"]
        if aid in definitions and definitions[aid] != definition:
            raise InputError("CONFLICTING_FACT_TYPE", "planning.activities", f"Inconsistent type or unit for {aid}")
        definitions[aid] = definition

    prepared = []
    for candidate in candidates:
        facts = [dict(fact) for fact in candidate["attributes"]]
        cost = candidate["estimated_cost_minor"]
        facts.append({"attribute_id": "estimated_cost", "value": cost, "value_type": "integer",
                      "unit": f"{candidate['currency']}_minor", "status": candidate["cost_status"],
                      "source": candidate["cost_source"]})
        for fact in facts:
            register({"attribute_id": fact["attribute_id"], "value_type": fact["value_type"], "unit": fact.get("unit")})
        prepared.append({key: value for key, value in candidate.items() if key not in {"attributes", "cost_status", "cost_source"}})
        prepared[-1]["facts"] = facts
    for question in questions:
        for aid in question["supported_attributes"]:
            register({"attribute_id": aid, "value_type": "category", "unit": None})
        binding = question["semantic_binding"]
        if binding is not None:
            register({key: binding[key] for key in ("attribute_id", "value_type", "unit")})
    return prepared, [definitions[key] for key in sorted(definitions)]
