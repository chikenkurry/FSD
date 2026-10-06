"""Execution contract shared by preprocessing and the activity/time algorithm."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


SCHEMA_VERSION = "activity-v2"
UTILITY_RULES = ("rating_v1", "attribute_match_v1", "neutral_v1")
FACT_STATUSES = ("confirmed", "estimated", "unknown")
VALUE_TYPES = ("integer", "number", "category", "boolean")
DEFAULT_OBJECTIVE = {
    "mode": "maximin_then_average",
    "minimum_score_weight": 0.6,
    "average_score_weight": 0.4,
    "fairness_weight": 0.0,
}
TIE_BREAKERS = ["lowest_estimated_cost", "earliest_start", "stable_candidate_id"]
MISSING_VALUE_POLICY = {
    "missing_budget": "incomplete",
    "missing_rating": "incomplete",
    "missing_required_attribute": "unresolved",
    "missing_availability": "unavailable",
    "no_preference": "neutral",
}


class ContractError(ValueError):
    """An execution handoff is malformed or uses an unsupported policy."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def object_value(value: Any, path: str) -> dict:
    require(isinstance(value, dict), f"{path} must be an object")
    return value


def rows(value: Any, path: str) -> list[dict]:
    require(isinstance(value, list), f"{path} must be a list")
    for row in value:
        object_value(row, path)
    return value


def text_id(value: Any, path: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{path} must be nonempty text")
    return value


def index_rows(value: Any, key: str, path: str) -> dict[str, dict]:
    indexed = {}
    for row in rows(value, path):
        identifier = text_id(row.get(key), f"{path}.{key}")
        require(identifier not in indexed, f"duplicate {path}.{key}: {identifier}")
        indexed[identifier] = row
    return indexed


def finite_nonnegative(value: Any, path: str) -> None:
    require(type(value) in {int, float} and (type(value) is int or math.isfinite(value)) and value >= 0 and value <= 1e308,
            f"{path} must be finite and nonnegative")


def timestamp(value: Any) -> datetime:
    text_id(value, "timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"invalid timestamp: {value}") from exc
    require(parsed.utcoffset() is not None, "timestamps must include a timezone offset")
    return parsed


def validate_value(value: Any, definition: dict, path: str) -> None:
    kind = definition.get("value_type")
    require(kind in VALUE_TYPES, f"unsupported value type at {path}")
    if kind == "category":
        text_id(value, path)
        allowed = definition.get("allowed_values")
        if allowed is not None:
            require(isinstance(allowed, list) and all(isinstance(v, str) for v in allowed),
                    f"{path}.allowed_values must contain text")
            require(value in allowed, f"unsupported category at {path}")
    elif kind == "boolean":
        require(type(value) is bool, f"{path} must be boolean")
    elif kind == "integer":
        require(type(value) is int, f"{path} must be an integer")
    else:
        require(type(value) in {int, float} and (type(value) is int or math.isfinite(value)), f"{path} must be finite numeric data")


def group_objective(value: Any = None) -> dict:
    supplied = object_value({} if value is None else value, "group_objective")
    require(set(supplied) <= set(DEFAULT_OBJECTIVE), "unknown group objective field")
    policy = {**DEFAULT_OBJECTIVE, **supplied}
    require(policy["mode"] in ("maximin_then_average", "weighted_fairness"), "unsupported group objective mode")
    for field in ("minimum_score_weight", "average_score_weight", "fairness_weight"):
        finite_nonnegative(policy[field], field)
    require(math.isfinite(policy["minimum_score_weight"] + policy["average_score_weight"]),
            "group score weights overflow")
    if policy["mode"] == "weighted_fairness":
        require(policy["minimum_score_weight"] + policy["average_score_weight"] > 0,
                "weighted fairness needs a positive score weight")
    return policy


def ranking_order(objective: dict) -> list[str]:
    primary = ["highest_min_member_score", "highest_average_member_score"]
    if objective["mode"] == "weighted_fairness":
        primary.insert(0, "highest_group_score")
    return primary + TIE_BREAKERS


def candidate_fact(candidate: dict, attribute_id: str) -> dict | None:
    return next((fact for fact in candidate["facts"] if fact["attribute_id"] == attribute_id), None)


def applies(preference: dict, candidate: dict) -> bool:
    scope = preference["scope"]
    return scope == "all" or preference[f"{scope}_id"] == candidate.get(f"{scope}_id")


def _provenance(entry: dict, questions: dict, hard: bool) -> None:
    qid = entry.get("source_question_id")
    require(isinstance(qid, str) and qid in questions, "answer references an unknown question")
    require(questions[qid]["is_hard_constraint"] is hard, "answer references the wrong question type")
    text_id(entry.get("source_answer_id"), "source_answer_id")
    require(entry.get("source_type") in ("member_response", "semantic_model"), "unsupported answer source")
    text_id(entry.get("evidence"), "answer evidence")


def _attribute(entry: dict, criteria: dict, value_field: str, question: dict) -> None:
    aid = entry.get("attribute_id")
    require(isinstance(aid, str) and aid in criteria and aid != "estimated_cost", "unsupported attribute criterion")
    require(aid in question["criteria"], "attribute is outside the source question mapping")
    validate_value(entry.get(value_field), criteria[aid], value_field)


def _candidates(candidates: dict, criteria: dict) -> None:
    for candidate in candidates.values():
        text_id(candidate.get("activity_id"), "candidate.activity_id")
        if "scenario_id" in candidate:
            text_id(candidate["scenario_id"], "candidate.scenario_id")
        require(timestamp(candidate.get("end_at")) > timestamp(candidate.get("start_at")), "invalid candidate time range")
        currency = text_id(candidate.get("currency"), "candidate.currency")
        facts = index_rows(candidate.get("facts"), "attribute_id", "candidate facts")
        for aid, fact in facts.items():
            require(aid in criteria, f"unsupported candidate criterion: {aid}")
            definition = criteria[aid]
            require(fact.get("value_type") == definition["value_type"] and fact.get("unit") == definition.get("unit"),
                    f"inconsistent fact type or unit: {aid}")
            require(fact.get("status") in FACT_STATUSES, f"unsupported fact status: {aid}")
            text_id(fact.get("source"), "fact.source")
            if fact["status"] == "unknown":
                require(fact.get("value") is None, "unknown facts must have a null value")
            else:
                validate_value(fact.get("value"), definition, f"fact.{aid}")
        require("estimated_cost" in facts, "candidate needs a typed cost fact")
        cost = facts["estimated_cost"]
        require(cost["value_type"] == "integer" and cost.get("unit") == f"{currency}_minor", "cost currency or unit mismatch")
        require(cost["value"] is None or cost["value"] >= 0, "cost must be nonnegative")
        require(candidate.get("estimated_cost_minor") == cost["value"], "cost summary conflicts with typed fact")


def _questions(model: dict, criteria: dict) -> dict:
    questions = index_rows(model.get("questions"), "question_id", "questions")
    weights = []
    for question in questions.values():
        mapped = question.get("criteria")
        require(isinstance(mapped, list) and all(isinstance(aid, str) and aid in criteria for aid in mapped),
                "question references unsupported criteria")
        require(len(mapped) == len(set(mapped)), "duplicate question criteria")
        hard = question.get("is_hard_constraint")
        require(type(hard) is bool, "question needs is_hard_constraint")
        if hard:
            require(question.get("weight") is None and question.get("utility_rule") is None,
                    "hard questions cannot carry weights or utility rules")
        else:
            finite_nonnegative(question.get("weight"), "question.weight")
            weights.append(question["weight"])
            require(question.get("utility_rule") in UTILITY_RULES, "unsupported question utility rule")
            require(question.get("aggregation") in ("direct", "average"), "unsupported question aggregation")
            require(question.get("missing_value_policy") == "unresolved", "unsupported question missing value policy")
    if weights:
        require(math.isclose(sum(weights), 1.0, abs_tol=1e-9), "soft question weights must sum to one")
    objective = group_objective(model.get("group_objective"))
    require(model.get("group_objective") == objective, "group objective must specify all policy fields")
    ranking = object_value(model.get("ranking_policy"), "ranking_policy")
    require(ranking.get("feasibility_policy") == "all_required_participants", "unsupported feasibility policy")
    require(ranking.get("sort_order") == ranking_order(objective), "ranking order conflicts with group objective")
    require(model.get("missing_value_policy") == MISSING_VALUE_POLICY, "unsupported missing value policy")
    return questions


def _constraints(constraints: dict, participants: dict, candidates: dict, criteria: dict, questions: dict) -> None:
    require(set(constraints) == set(participants), "constraints must cover the participant roster exactly once")
    for constraint in constraints.values():
        availability = object_value(constraint.get("availability"), "availability")
        for source in rows(constraint.get("answer_sources", []), "constraint.answer_sources"):
            _provenance(source, questions, True)
        for interval in rows(availability.get("available_intervals"), "available_intervals"):
            require(timestamp(interval.get("end_at")) > timestamp(interval.get("start_at")), "invalid availability interval")
        budget = object_value(constraint.get("budget"), "budget")
        require(budget.get("kind") in ("limited", "unlimited", "missing"), "unsupported budget kind")
        if budget["kind"] == "limited":
            amount = budget.get("max_cost_minor")
            require(type(amount) is int and amount >= 0, "budget must be nonnegative minor units")
            currency = text_id(budget.get("currency"), "budget.currency")
            require(all(c["currency"] == currency for c in candidates.values()), "budget currency mismatch")
        requirements = rows(constraint.get("required_attributes"), "required_attributes")
        seen = {}
        for requirement in requirements:
            _provenance(requirement, questions, True)
            _attribute(requirement, criteria, "required_value", questions[requirement["source_question_id"]])
            require(requirement.get("participant_id") == constraint["participant_id"], "requirement participant mismatch")
            require(requirement.get("confirmation_status") == "confirmed" and requirement.get("status") == "confirmed",
                    "hard requirement needs confirmation")
            aid = requirement["attribute_id"]
            require(aid not in seen or seen[aid] == requirement["required_value"], "conflicting hard requirements")
            seen[aid] = requirement["required_value"]
        flags = index_rows(constraint.get("candidate_flags"), "candidate_id", "candidate flags")
        for cid, flag in flags.items():
            require(cid in candidates, "flag references an unknown candidate")
            _provenance(flag, questions, True)
            require(flag.get("flag") in ("cannot_join", "needs_information"), "unsupported candidate flag")


def _preferences(preferences: list[dict], participants: dict, candidates: dict, criteria: dict, questions: dict, activity_ids: set[str]) -> None:
    seen = set()
    targets = {scope: {c.get(f"{scope}_id") for c in candidates.values()} - {None}
               for scope in ("activity", "candidate", "scenario")}
    targets["activity"] = activity_ids
    for preference in preferences:
        require(isinstance(preference.get("participant_id"), str) and preference["participant_id"] in participants, "unknown preference participant")
        _provenance(preference, questions, False)
        scope = preference.get("scope")
        require(scope in ("all", *targets), "unsupported preference scope")
        if scope != "all":
            target = preference.get(f"{scope}_id")
            require(isinstance(target, str) and target in targets[scope], "unknown preference target")
        require(all(f"{other}_id" not in preference for other in targets if other != scope),
                "preference contains a target outside its scope")
        kind = preference.get("kind")
        require(isinstance(kind, str), "preference kind must be text")
        rule = {"rating": "rating_v1", "attribute_preference": "attribute_match_v1", "indifferent": "neutral_v1"}.get(kind)
        require(rule is not None and preference.get("utility_rule") == rule, "unsupported preference utility rule")
        question = questions[preference["source_question_id"]]
        require(kind == "indifferent" or rule == question["utility_rule"], "preference and question utility rules conflict")
        require(preference.get("status") in (("explicitly_indifferent",) if kind == "indifferent" else ("confirmed", "estimated")),
                "preference is unresolved")
        if kind == "rating":
            require(scope != "all", "ratings need an explicit target")
            require(type(preference.get("rating")) is int and 0 <= preference["rating"] <= 4, "invalid rating")
        elif kind == "attribute_preference":
            _attribute(preference, criteria, "preferred_value", question)
        key = (preference["participant_id"], preference["source_question_id"], scope,
               preference.get(f"{scope}_id"), preference.get("attribute_id"))
        require(key not in seen, "duplicate or conflicting preferences")
        seen.add(key)
    for candidate in candidates.values():
        groups = {}
        for preference in preferences:
            if applies(preference, candidate):
                key = (preference["participant_id"], preference["source_question_id"])
                groups.setdefault(key, []).append(preference)
        for (_, qid), answers in groups.items():
            require(questions[qid]["aggregation"] != "direct" or len(answers) == 1,
                    "direct aggregation requires one applicable answer")
            require(len(answers) == 1 or all(a["kind"] != "indifferent" for a in answers),
                    "indifference conflicts with another applicable preference")
            attributes = [a["attribute_id"] for a in answers if a["kind"] == "attribute_preference"]
            require(len(attributes) == len(set(attributes)), "overlapping attribute preferences")


def validate_handoff(data: Any) -> None:
    data = object_value(data, "algorithm input")
    context = object_value(data.get("context"), "context")
    require(context.get("schema_version") == SCHEMA_VERSION, "unsupported execution schema version")
    participants = index_rows(data.get("participants"), "participant_id", "participants")
    require(bool(participants), "participant roster must not be empty")
    for participant in participants.values():
        require(type(participant.get("is_required_for_decision")) is bool, "participant needs required status")
        require(participant.get("response_status") in ("complete", "incomplete", "stale", "needs_clarification"), "invalid response status")
    require(any(p["is_required_for_decision"] for p in participants.values()), "at least one required participant is needed")
    criteria = index_rows(data.get("criteria"), "attribute_id", "criteria")
    for definition in criteria.values():
        require(definition.get("value_type") in VALUE_TYPES, "unsupported criterion type")
        if definition.get("unit") is not None:
            text_id(definition["unit"], "criterion.unit")
    candidates = index_rows(data.get("candidates"), "candidate_id", "candidates")
    activity_ids = context.get("activity_ids")
    require(isinstance(activity_ids, list) and all(isinstance(aid, str) and aid.strip() for aid in activity_ids),
            "context needs the activity inventory")
    require(len(activity_ids) == len(set(activity_ids)), "duplicate activity inventory")
    require(all(c.get("activity_id") in activity_ids for c in candidates.values()), "unknown candidate activity")
    _candidates(candidates, criteria)
    questions = _questions(object_value(data.get("scoring_model"), "scoring_model"), criteria)
    _constraints(index_rows(data.get("constraints"), "participant_id", "constraints"), participants, candidates, criteria, questions)
    _preferences(rows(data.get("preferences"), "preferences"), participants, candidates, criteria, questions, set(activity_ids))
