"""Normalize each answer meaning against its own criterion definition."""

from __future__ import annotations

import re
from decimal import Decimal

from .common import InputError, require_in, require_text
from .comparatives import comparative_direction
from .durations import validate_duration
from .generic_mapping import interpretation_mapping
from .generic_values import INTENTS, TARGET_PATTERN, grounded_numeric_bound, numeric_semantics


def _normalize_numeric_meaning(item: dict, question: dict, definition: dict, criterion: str, path: str,
                               *, model_derived: bool) -> dict:
    grounded = grounded_numeric_bound(item, definition, path)
    literal_bound = grounded is not item
    item = grounded
    direction = comparative_direction(item.get("evidence", "")) if model_derived and not literal_bound else None
    if direction:
        # Repair a model's target/match label only from the item's own
        # grounded clause. Requirement strength is checked separately.
        item = {**item, "intent": direction, "value": "", "polarity": "prefer"}
    value, intent = item["value"], item.get("intent", "match")
    original_value = value
    declared_intent = intent if intent != "match" and not model_derived else None
    intent, value = numeric_semantics(value, definition, path, intent)
    intent_source = "semantic_model" if model_derived else "answer"
    try:
        literal_intent, _ = numeric_semantics(original_value, definition, path)
    except InputError:
        literal_intent = None
    literal_target = isinstance(original_value, str) and re.match(TARGET_PATTERN, original_value.strip(), re.I)
    evidence_target = model_derived and re.search(r"\b(?:ideal|ideally|target|exactly)\b", item.get("evidence", ""), re.I)
    if literal_intent == "target" and not literal_target and not literal_bound and not evidence_target and declared_intent is None:
        question_intent = question.get("numeric_intent") if criterion == question["criterion"] else None
        if question_intent is None:
            raise InputError("AMBIGUOUS_NUMERIC_INTENT", path,
                             "Specify an ideal target, minimum/maximum, range, or higher/lower direction; a bare number does not establish intent")
        intent, value = numeric_semantics(original_value, definition, path, question_intent)
        intent_source = "question"
    return {**item, "intent": intent, "value": value, "intent_source": intent_source}


def prepare_meaning(item: dict, question: dict, registry: dict, candidates: list[dict],
                    context: dict, path: str, *, model_derived: bool = False) -> dict:
    criterion = require_text(item.get("criterion", question["criterion"]), path)
    value = item.get("value")
    intent = require_in(item.get("intent", "match"), INTENTS, path)
    if criterion not in registry and criterion not in {"max_cost", "duration_days", "availability"}:
        # A typed member value can describe the fact we need to request. It
        # does not establish that any option has that value.
        kind, unit = "tag_set", None
        if type(value) is bool or isinstance(value, str) and value.casefold() in {"true", "false"}:
            kind = "boolean"
        elif type(value) in {int, float} or intent in {"target", "maximize", "minimize", "range", "maximum", "minimum", "less_than", "greater_than"}:
            kind = "number"
            if isinstance(value, str):
                match = re.search(r"\d\s+([A-Za-z]+)$", value.strip())
                unit = match.group(1) if match else None
        unit = item.get("unit", unit)
        registry[criterion] = {"attribute_id": criterion, "value_type": kind, "unit": unit}
    hard = item.get("must_have", False) or question["role"] == "hard" and criterion == question["criterion"]
    definition = registry.get(criterion)
    if item.get("unit") is not None and definition and item["unit"] != definition["unit"]:
        raise InputError("UNIT_MISMATCH", path, "Interpretation unit differs from declared criterion unit")
    if criterion in {"max_cost", "duration_days"} or definition and definition["value_type"] in {"number", "decimal"}:
        definition = definition or {"value_type": "decimal" if criterion == "max_cost" else "number",
                                    "unit": context["currency"] if criterion == "max_cost" else "days"}
        item = _normalize_numeric_meaning(item, question, definition, criterion, path, model_derived=model_derived)
        intent, value = item["intent"], item["value"]
        if criterion == "max_cost":
            endpoints = [value.get("lower"), value.get("upper")] if isinstance(value, dict) else [value]
            if any(endpoint is not None and Decimal(str(endpoint)) < 0 for endpoint in endpoints):
                raise InputError("AMBIGUOUS_BUDGET", path, "Budget limits must be nonnegative")
        if criterion == "duration_days":
            validate_duration(value, path, interval=isinstance(value, dict))
    elif criterion == "availability":
        raise InputError("AMBIGUOUS_AVAILABILITY", path, "Provide availability through a date question with exact date intervals")
    elif intent not in {"match", "target"}:
        raise InputError("AMBIGUOUS_ANSWER", path, "Numeric direction or range needs a numeric criterion")
    mapping = interpretation_mapping(question, criterion, registry, candidates, context, intent, hard)
    if hard and mapping["status"] == "unresolved" and intent in {"match", "target"}:
        mapping = interpretation_mapping(question, criterion, registry, candidates, context, "equals", hard)
    return {**item, "criterion": criterion, "value": value, "intent": intent, "mapping": mapping, "is_hard": hard}
