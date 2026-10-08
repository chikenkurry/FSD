"""Parse numeric targets, directions, and inclusive or exclusive ranges."""

from __future__ import annotations

import re
from decimal import Decimal

from .common import InputError
from .generic_mapping import normalize_answer, token
from .money import parse_amount


INTENTS = {"match", "target", "maximize", "minimize", "range", "maximum", "minimum", "less_than", "greater_than"}
BOUND_RULES = {"maximum": "maximum_v1", "minimum": "minimum_v1", "less_than": "less_than_v1", "greater_than": "greater_than_v1"}
BOUND_WORDS = {
    "at least": "minimum", "minimum": "minimum", "no less than": "minimum",
    "at most": "maximum", "maximum": "maximum", "no more than": "maximum",
    "under": "less_than", "less than": "less_than", "over": "greater_than",
    "more than": "greater_than", "greater than": "greater_than",
}
BOUND_PATTERN = "|".join(re.escape(word) for word in sorted(BOUND_WORDS, key=len, reverse=True))
TARGET_PATTERN = r"(?:exactly|ideally|ideal(?:ly)?(?: about)?|target(?: of)?|aim(?:ing)? for)\s+"


def grounded_numeric_bound(item: dict, mapping: dict, path: str) -> dict:
    """Use a literal bound in the item's clause before a model's intent label.

    Criterion selection still comes from semantic extraction. Negated boundaries
    need clarification; this parser does not guess which inequality to invert.
    """
    evidence = item.get("evidence", "")
    match = re.search(r"\b(" + BOUND_PATTERN + r")\s+(.+)$", evidence, re.I)
    if match is None:
        return item
    prefix = evidence[:match.start()]
    if re.search(r"\b(not|never|cannot|avoid|dislike|hate)\b|\b(can't|don't)\b", prefix, re.I):
        raise InputError("AMBIGUOUS_ANSWER", path, "Clarify the negated numeric boundary")
    # Reject compound leftovers rather than borrowing a number from another
    # criterion. Scoping normally narrows the evidence before reaching here.
    value = match.group(2).strip(" .")
    try:
        numeric_value(value, mapping, path)
    except InputError as exc:
        if exc.code == "UNIT_MISMATCH":
            raise
        return item
    return {**item, "intent": BOUND_WORDS[match.group(1).casefold()], "value": value, "polarity": "prefer"}


def numeric_value(value: object, mapping: dict, path: str) -> object:
    if mapping["value_type"] == "decimal":
        return parse_amount(value, mapping.get("unit"), path)
    return normalize_answer(value, mapping, path)


def numeric_semantics(value: object, mapping: dict, path: str, intent: str = "match") -> tuple[str, object]:
    """Return member meaning, without calculating option utility or feasibility."""
    if intent not in INTENTS:
        raise InputError("INVALID_VALUE", path, "Unknown numeric preference intent")
    if isinstance(value, dict) and "direction" in value:
        if set(value) != {"direction"} or value["direction"] not in {"maximize", "minimize"}:
            raise InputError("INVALID_VALUE", path, "Direction must be maximize or minimize")
        return value["direction"], None
    if intent in {"maximize", "minimize"}:
        return intent, None
    if isinstance(value, str):
        text = token(value)
        target = re.fullmatch(TARGET_PATTERN + r"(.+)", text)
        if target:
            return "target", numeric_value(target.group(1), mapping, path)
        if not re.search(r"\bthan\b", text) and re.fullmatch(r"(?:prefer )?(?:greater|higher|larger|longer|more)(?: is better| [a-z_ ]+)?|maximize", text):
            return "maximize", None
        if not re.search(r"\bthan\b", text) and re.fullmatch(r"(?:prefer )?(?:lower|smaller|shorter|less|cheaper)(?: is better| [a-z_ ]+)?|minimize", text):
            return "minimize", None
        bound = re.fullmatch(r"(" + BOUND_PATTERN + r")\s+(.+)", text)
        if bound:
            operation = BOUND_WORDS[bound.group(1)]
            return operation, numeric_value(bound.group(2), mapping, path)
        interval = re.fullmatch(r"(?:between\s+)?([+-]?\d+(?:\.\d+)?)\s*(?:to|and|[-–])\s*([+-]?\d+(?:\.\d+)?)\s*(.*)", text)
        if interval:
            unit = interval.group(3)
            value = {"lower": interval.group(1) + (" " + unit if unit else ""),
                     "upper": interval.group(2) + (" " + unit if unit else "")}
            intent = "range"
    if isinstance(value, dict):
        if set(value) - {"lower", "upper", "lower_inclusive", "upper_inclusive"}:
            raise InputError("INVALID_VALUE", path, "Unknown numeric range field")
        bounds = {key: numeric_value(value[key], mapping, path) if value.get(key) is not None else None
                  for key in ("lower", "upper")}
        if bounds["lower"] is None and bounds["upper"] is None:
            raise InputError("AMBIGUOUS_ANSWER", path, "A range needs at least one endpoint")
        if bounds["lower"] is not None and bounds["upper"] is not None and Decimal(str(bounds["lower"])) > Decimal(str(bounds["upper"])):
            raise InputError("CONFLICTING_ANSWER", path, "Range endpoints are reversed")
        for key in ("lower_inclusive", "upper_inclusive"):
            bounds[key] = value.get(key, True)
            if type(bounds[key]) is not bool:
                raise InputError("INVALID_VALUE", path, "Range inclusivity must be boolean")
        if (bounds["lower"] == bounds["upper"] and bounds["lower"] is not None
                and not (bounds["lower_inclusive"] and bounds["upper_inclusive"])):
            raise InputError("CONFLICTING_ANSWER", path, "An open interval with equal endpoints is empty")
        return "range", bounds
    if intent == "range":
        raise InputError("AMBIGUOUS_ANSWER", path, "Specify the range endpoints")
    return intent if intent in BOUND_RULES else "target", numeric_value(value, mapping, path)


def intersect_numeric_requirements(requirements: list[tuple[str, object]], path: str) -> dict:
    """Intersect typed limits exactly; keep the winning endpoints' original types."""
    combined = {"lower": None, "upper": None, "lower_inclusive": True, "upper_inclusive": True}
    for rule, value in requirements:
        interval = {"lower": None, "upper": None, "lower_inclusive": True, "upper_inclusive": True}
        if rule == "within_range_v1":
            interval = value
        if rule in {"minimum_v1", "greater_than_v1", "equals_v1"}:
            interval.update(lower=value, lower_inclusive=rule != "greater_than_v1")
        if rule in {"maximum_v1", "less_than_v1", "equals_v1"}:
            interval.update(upper=value, upper_inclusive=rule != "less_than_v1")
        for endpoint in ("lower", "upper"):
            candidate, current = interval[endpoint], combined[endpoint]
            if candidate is None:
                continue
            tighter = current is None or (Decimal(str(candidate)) > Decimal(str(current)) if endpoint == "lower"
                                          else Decimal(str(candidate)) < Decimal(str(current)))
            inclusive = endpoint + "_inclusive"
            if tighter:
                combined.update({endpoint: candidate, inclusive: interval[inclusive]})
            elif Decimal(str(candidate)) == Decimal(str(current)):
                combined[inclusive] = combined[inclusive] and interval[inclusive]
    lower, upper = combined["lower"], combined["upper"]
    if lower is not None and upper is not None and (Decimal(str(lower)) > Decimal(str(upper)) or
            Decimal(str(lower)) == Decimal(str(upper)) and not (combined["lower_inclusive"] and combined["upper_inclusive"])):
        raise InputError("CONFLICTING_ANSWER", path, "Numeric requirements have no overlapping values")
    return combined


def preference_range(intent: str, value: object) -> dict:
    if intent == "range":
        return value
    lower = intent in {"minimum", "greater_than"}
    return {"lower": value if lower else None, "upper": None if lower else value,
            "lower_inclusive": intent != "greater_than", "upper_inclusive": intent != "less_than"}
