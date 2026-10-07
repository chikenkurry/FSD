"""Normalize each answer meaning against its own criterion definition."""

from __future__ import annotations

import re
from decimal import Decimal

from .common import InputError, require_in, require_text
from .generic_mapping import interpretation_mapping
from .generic_values import INTENTS, grounded_numeric_bound, numeric_semantics


def prepare_meaning(item: dict, question: dict, registry: dict, candidates: list[dict],
                    context: dict, path: str) -> dict:
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
        item = grounded_numeric_bound(item, definition, path)
        value, intent = item["value"], item.get("intent", intent)
        intent, value = numeric_semantics(value, definition, path, intent)
        if criterion == "max_cost":
            endpoints = [value.get("lower"), value.get("upper")] if isinstance(value, dict) else [value]
            if any(endpoint is not None and Decimal(str(endpoint)) < 0 for endpoint in endpoints):
                raise InputError("AMBIGUOUS_BUDGET", path, "Budget limits must be nonnegative")
        if criterion == "duration_days":
            endpoints = [value.get("lower"), value.get("upper")] if isinstance(value, dict) else [value]
            if any(endpoint is not None and not 1 <= endpoint <= 365 for endpoint in endpoints):
                raise InputError("AMBIGUOUS_DURATION", path, "Duration must be between 1 and 365 days")
    elif criterion == "availability":
        raise InputError("AMBIGUOUS_AVAILABILITY", path, "Provide availability through a date question with exact date intervals")
    elif intent not in {"match", "target"}:
        raise InputError("AMBIGUOUS_ANSWER", path, "Numeric direction or range needs a numeric criterion")
    mapping = interpretation_mapping(question, criterion, registry, candidates, context, intent, hard)
    if hard and mapping["status"] == "unresolved" and intent in {"match", "target"}:
        mapping = interpretation_mapping(question, criterion, registry, candidates, context, "equals", hard)
    return {**item, "criterion": criterion, "value": value, "intent": intent, "mapping": mapping, "is_hard": hard}
