"""Typed question mappings built from declared facts and plan semantics.

These declarations describe comparisons for a generic algorithm. They do not
calculate candidate scores or decide feasibility.
"""

from __future__ import annotations

import re
from decimal import Decimal

from .common import InputError, require_in, require_list, require_object, require_text
from .money import decimal_string as decimal_value


TYPES = {"number", "decimal", "category", "boolean", "tag_set", "date_intervals"}
SOFT_RULES = {
    "number": "numeric_target_v1", "decimal": "numeric_target_v1",
    "category": "attribute_match_v1", "boolean": "attribute_match_v1", "tag_set": "tag_overlap_v1",
}
NUMERIC_SOFT_RULES = {"numeric_target_v1", "numeric_maximize_v1", "numeric_minimize_v1", "numeric_range_v1"}
QUESTION_NUMERIC_INTENTS = {"target", "minimum", "maximum", "less_than", "greater_than", "maximize", "minimize", "range"}
INTENT_RULES = {
    "target": "numeric_target_v1", "maximize": "numeric_maximize_v1", "minimize": "numeric_minimize_v1",
    "minimum": "numeric_range_v1", "maximum": "numeric_range_v1", "less_than": "numeric_range_v1",
    "greater_than": "numeric_range_v1", "range": "numeric_range_v1",
}
HARD_RULES = {
    "number": {"maximum_v1", "minimum_v1", "equals_v1", "less_than_v1", "greater_than_v1", "within_range_v1"},
    "decimal": {"maximum_v1", "minimum_v1", "equals_v1", "less_than_v1", "greater_than_v1", "within_range_v1"},
    "category": {"equals_v1"}, "boolean": {"equals_v1"},
    "tag_set": {"contains_all_v1"}, "date_intervals": {"date_overlap_v1"},
}
NUMBER_RE = re.compile(r"\s*(?:at least|at most|maximum|minimum|exactly)?\s*([+-]?\d+(?:\.\d+)?)\s*(.*?)\s*", re.I)
HARD_QUESTION = re.compile(
    r"\b(?:must|need|require|required|mandatory|essential|maximum|minimum|limit|ceiling|"
    r"at least|at most|no more than|no less than|cannot|only if|non-negotiable)\b", re.I,
)


def model_question_role(assessment: dict, label: str) -> dict:
    """Require explicit limit wording before a model can make a question hard."""
    if (assessment.get("role") == "hard" and assessment.get("criterion") not in {"availability", "max_cost"}
            and not HARD_QUESTION.search(label)):
        return {**assessment, "role": "soft", "relevance": assessment.get("relevance") or 0.5,
                "reason": "No explicit feasibility limit; treated as a soft question. " + str(assessment.get("reason", ""))}
    return assessment


def token(value: str) -> str:
    return " ".join(value.casefold().split())


def infer_type(value: object, path: str) -> str:
    if type(value) is bool:
        return "boolean"
    if type(value) in {int, float}:
        return "number"
    if isinstance(value, str):
        return "category"
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        return "tag_set"
    raise InputError("INVALID_FACT", path, "Facts need a scalar value or a list of text tags")


def typed_value(value: object, kind: str, path: str) -> object:
    if kind == "number":
        if type(value) not in {int, float} or not -1e308 <= value <= 1e308:
            raise InputError("INVALID_VALUE", path, "Expected a finite number")
        return value
    if kind == "decimal":
        return decimal_value(value, path)
    if kind == "boolean":
        if type(value) is not bool:
            raise InputError("INVALID_VALUE", path, "Expected a boolean")
        return value
    if kind == "category":
        return token(require_text(value, path))
    if kind == "tag_set":
        values = require_list(value, path)
        if not values:
            raise InputError("INVALID_VALUE", path, "Expected one or more tags")
        return sorted({token(require_text(v, path)) for v in values})
    raise InputError("UNSUPPORTED_CRITERION", path, "Unsupported typed value")


def fact_registry(candidates: list[dict]) -> dict[str, dict]:
    registry = {}
    for candidate in candidates:
        for fact in candidate["facts"]:
            aid = fact["criterion"]
            if aid == "max_cost":
                kind = "decimal"
            else:
                kind = fact.get("value_type") or infer_type(fact["value"], "planning.options.facts")
            kind = require_in(kind, TYPES - {"date_intervals"}, "planning.options.facts.value_type")
            definition = {"attribute_id": aid, "value_type": kind, "unit": fact.get("unit")}
            if aid in registry and registry[aid] != definition:
                raise InputError("CONFLICTING_FACT_TYPE", "planning.options.facts", f"Type or unit differs for {aid}")
            if fact["status"] != "unknown":
                typed_value(fact["value"], kind, "planning.options.facts.value")
            registry[aid] = definition
    return registry


def local_question(label: str, registry: dict) -> dict | None:
    """Bind unambiguous question wording to an existing fact criterion."""
    words = set(re.findall(r"\w+", label.casefold()))
    if words & {"important", "importance", "rate", "rating"}:
        return None
    matches = [aid for aid in registry if set(aid.split("_")) <= words]
    if len(matches) != 1:
        return None
    aid = matches[0]
    hard = bool(re.search(r"\b(must|require|required|maximum|minimum|at least|at most)\b", label.casefold()))
    return {"role": "hard" if hard else "soft", "criterion": aid,
            "relevance": 0.0 if hard else 0.5, "reason": "Question names a supplied fact criterion"}


def question_numeric_intent(question: dict, supplied: object = None) -> tuple[str | None, str | None]:
    """Use explicit declarations or narrow wording rules, never an LLM guess."""
    if "numeric_intent" in question:
        return require_in(question["numeric_intent"], QUESTION_NUMERIC_INTENTS, "question.numeric_intent"), "leader"
    rule = supplied.get("comparison_rule") if isinstance(supplied, dict) else None
    by_rule = {"numeric_target_v1": "target", "numeric_maximize_v1": "maximize", "numeric_minimize_v1": "minimize",
               "maximum_v1": "maximum", "minimum_v1": "minimum", "less_than_v1": "less_than",
               "greater_than_v1": "greater_than", "equals_v1": "target", "within_range_v1": "range"}
    if isinstance(rule, str) and rule in by_rule:
        return by_rule[rule], "leader_mapping"
    label = question["label"].casefold()
    for pattern, intent in (
        (r"\b(at least|minimum|no less than)\b", "minimum"),
        (r"\b(at most|maximum|no more than)\b", "maximum"),
        (r"\b(ideal|ideally|target|exactly)\b", "target"),
        (r"\b(maximize|longer is better|higher is better)\b", "maximize"),
        (r"\b(minimize|cheaper is better|lower is better)\b", "minimize"),
    ):
        if re.search(pattern, label):
            return intent, "question_wording"
    if question["role"] == "hard" and question["criterion"] == "max_cost":
        return "maximum", "budget_question"
    return None, None


def resolve_mapping(question: dict, registry: dict, candidates: list[dict], context: dict, supplied: object = None) -> dict:
    aid, role = question["criterion"], question["role"]
    if role in {"informational", "importance", "unclassified"}:
        return {"status": "unresolved" if role == "unclassified" else "not_applicable"}
    canonical = {
        "availability": {"attribute_id": aid, "value_type": "date_intervals", "unit": "date"},
        "max_cost": {"attribute_id": aid, "value_type": "decimal", "unit": context["currency"]},
        "duration_days": {"attribute_id": aid, "value_type": "number", "unit": "days"},
    }
    if aid in canonical and aid in registry and registry[aid] != canonical[aid]:
        raise InputError("CONFLICTING_FACT_TYPE", "question.mapping", "Canonical criterion type or unit differs from the decision context")
    definition = registry.get(aid) or canonical.get(aid)
    supplied = require_object(supplied, "question.mapping") if supplied is not None else {}
    if set(supplied) - {"value_type", "unit", "comparison_rule", "scale"}:
        raise InputError("INVALID_MAPPING", "question.mapping", "Unknown mapping field")
    if definition is None:
        # An open interest can request tags without asserting that any option
        # possesses them. Known option facts always determine their own type.
        definition = {"attribute_id": aid, "value_type": supplied.get("value_type", "tag_set"),
                      "unit": supplied.get("unit")}
    for field in ("value_type", "unit"):
        if field in supplied and supplied[field] != definition[field]:
            raise InputError("CONFLICTING_FACT_TYPE", "question.mapping", f"Mapping {field} differs from option facts")
    kind = require_in(definition["value_type"], TYPES, "question.mapping.value_type")
    intent = question.get("numeric_intent")
    if intent is not None and kind not in {"number", "decimal"}:
        raise InputError("INVALID_MAPPING", "question.numeric_intent", "Numeric intent requires a numeric criterion")
    if definition["unit"] is not None:
        require_text(definition["unit"], "question.mapping.unit")
    registry[aid] = definition
    rule = SOFT_RULES.get(kind) if role == "soft" else next(iter(HARD_RULES[kind])) if len(HARD_RULES[kind]) == 1 else None
    if role == "hard" and kind in {"number", "decimal"}:
        label = question["label"].casefold()
        if aid == "max_cost" or re.search(r"\b(maximum|at most|max)\b", label):
            rule = "maximum_v1"
        elif re.search(r"\b(minimum|at least|min)\b", label):
            rule = "minimum_v1"
    if intent is not None:
        rule = INTENT_RULES[intent] if role == "soft" else {
            "target": "equals_v1", "minimum": "minimum_v1", "maximum": "maximum_v1", "less_than": "less_than_v1",
            "greater_than": "greater_than_v1", "range": "within_range_v1",
        }.get(intent)
        if role == "hard" and intent in {"maximize", "minimize"}:
            raise InputError("INVALID_MAPPING", "question.numeric_intent", "Hard numeric questions need a limit, not a direction")
        if "comparison_rule" in supplied and supplied["comparison_rule"] != rule:
            raise InputError("INVALID_MAPPING", "question.mapping", "Comparison rule contradicts the declared numeric intent")
    rule = supplied.get("comparison_rule", rule)
    allowed = NUMERIC_SOFT_RULES if role == "soft" and kind in {"number", "decimal"} else {SOFT_RULES[kind]} if role == "soft" and kind in SOFT_RULES else HARD_RULES[kind] if role == "hard" else set()
    if rule is None:
        return {"status": "unresolved", **definition}
    if not isinstance(rule, str) or rule not in allowed:
        raise InputError("UNSUPPORTED_UTILITY_RULE", "question.mapping", "Rule does not support the criterion type and role")
    if rule != "numeric_target_v1" and supplied.get("scale") is not None:
        raise InputError("INVALID_MAPPING", "question.mapping.scale", "Only numeric target comparisons use a scale")
    parameters = {}
    if rule in {"numeric_maximize_v1", "numeric_minimize_v1"}:
        values = [typed_value(f["value"], kind, "fact.value") for c in candidates for f in c["facts"]
                  if f["criterion"] == aid and f["status"] == "confirmed"]
        parameters = {"lower_bound": min(values, key=lambda v: Decimal(str(v))) if values else None,
                      "upper_bound": max(values, key=lambda v: Decimal(str(v))) if values else None}
    if rule == "numeric_target_v1":
        scale = supplied.get("scale")
        if scale is None:
            values = [float(typed_value(f["value"], kind, "fact.value")) for c in candidates for f in c["facts"]
                      if f["criterion"] == aid and f["status"] == "confirmed"]
            if not values and aid == "duration_days":
                values = [float(match.group(1)) for label in question["choices"].values()
                          if (match := re.fullmatch(r"(\d+)\s*days?", label, re.I))]
            scale = max(values) - min(values) if values else None
        if type(scale) not in {int, float} or not 0 < scale <= 1e308:
            return {"status": "unresolved", **definition}
        parameters["scale"] = scale
    return {"status": "resolved", **definition, "comparison_rule": rule, "parameters": parameters}


def interpretation_mapping(question: dict, criterion: str, registry: dict, candidates: list[dict], context: dict,
                           intent: str = "match", hard: bool = False) -> dict:
    """Build a comparison for one answer meaning without changing question weight."""
    base = {k: v for k, v in question.items() if k not in {"numeric_intent", "numeric_intent_source"}}
    base.update(criterion=criterion, role="hard" if hard else "soft")
    definition = registry.get(criterion)
    numeric = criterion in {"max_cost", "duration_days"} or definition and definition["value_type"] in {"number", "decimal"}
    rule = None
    if numeric:
        if hard:
            rule = {"target": "equals_v1", "range": "within_range_v1", "maximum": "maximum_v1", "minimum": "minimum_v1",
                    "less_than": "less_than_v1", "greater_than": "greater_than_v1", "equals": "equals_v1"}.get(intent)
        else:
            rule = {"target": "numeric_target_v1", "maximize": "numeric_maximize_v1", "minimize": "numeric_minimize_v1",
                    "range": "numeric_range_v1", "maximum": "numeric_range_v1", "minimum": "numeric_range_v1",
                    "less_than": "numeric_range_v1", "greater_than": "numeric_range_v1"}.get(intent)
    supplied = {"comparison_rule": rule} if rule else None
    if (criterion == question["criterion"] and intent in {"match", "target"} and not hard and question["role"] == "soft"
            and (not numeric or question["mapping"].get("comparison_rule") == "numeric_target_v1")):
        return question["mapping"]
    return resolve_mapping(base, registry, candidates, context, supplied)


def normalize_answer(value: object, mapping: dict, path: str) -> object:
    kind = mapping["value_type"]
    if kind == "tag_set":
        return typed_value(value if isinstance(value, list) else [value], kind, path)
    if kind == "boolean" and isinstance(value, str):
        normalized = token(value)
        if normalized in {"yes", "true"}:
            value = True
        elif normalized in {"no", "false"}:
            value = False
    if kind in {"number", "decimal"} and isinstance(value, str):
        match = NUMBER_RE.fullmatch(value)
        if match is None:
            raise InputError("AMBIGUOUS_ANSWER", path, "Provide a single numeric value in the declared unit")
        unit = match.group(2)
        if unit and token(unit) != token(mapping.get("unit") or ""):
            raise InputError("UNIT_MISMATCH", path, "Answer unit differs from the criterion unit")
        value = match.group(1)
        if kind == "number":
            value = float(value)
    return typed_value(value, kind, path)
