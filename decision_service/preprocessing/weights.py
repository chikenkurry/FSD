"""Relevance-based default question weights, with explicit leader overrides."""

from __future__ import annotations

import math
from collections import Counter

from .common import InputError


SOFT_KINDS = {"activity_rating", "open_preference", "semantic_preference"}


def option_relevance(question: dict, candidates: list[dict]) -> float:
    """Measure how much a mapped question can distinguish the known options.

    One activity counts once even when it has many start times. This is a
    transparent product policy, not a claim about personal importance.
    """
    activities = {candidate["activity_id"]: candidate for candidate in candidates}
    if not activities:
        return 0.0
    if "semantic_relevance" in question:
        return float(question["semantic_relevance"])
    if question["kind"] == "activity_rating":
        return 1.0
    if question["kind"] != "open_preference":
        return 0.0

    parts = []
    for attribute_id in question["supported_attributes"]:
        values = []
        for activity in activities.values():
            fact = next((a["value"] for a in activity["attributes"] if a["attribute_id"] == attribute_id), "unknown")
            if fact != "unknown":
                values.append(fact)
        coverage = len(values) / len(activities)
        distinction = 1.0 if len(set(values)) > 1 else 0.0
        parts.append(coverage * (0.25 + 0.75 * distinction))
    return sum(parts) / len(parts) if parts else 0.0


def resolve_weights(questions: list[dict], candidates: list[dict]) -> list[dict]:
    soft = [q for q in questions if q["kind"] in SOFT_KINDS]
    def topic_key(q: dict) -> tuple:
        if q["kind"] == "activity_rating":
            return ("rating",)
        if q["kind"] == "open_preference":
            return ("attributes", *sorted(q["supported_attributes"]))
        return ("semantic", q.get("semantic_criterion", q["label"]).casefold().strip())

    topic_counts = Counter(topic_key(q) for q in soft)
    supplied = [q for q in soft if q.get("leader_weight") is not None]
    leader_values = []
    for q in supplied:
        value = q["leader_weight"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise InputError("INVALID_WEIGHT", f"planning.questions.{q['question_id']}.leader_weight", "Weight must be finite and nonnegative")
        leader_values.append(float(value))
    leader_scale = max(1.0, *leader_values) if leader_values else 1.0

    raw_weights = {}
    relevances = {}
    sources = {}
    for q in soft:
        question_id = q["question_id"]
        relevance = option_relevance(q, candidates)
        if not math.isfinite(relevance) or relevance < 0 or relevance > 1:
            raise InputError("INVALID_RELEVANCE", f"planning.questions.{question_id}", "Relevance must be between 0 and 1")
        relevances[question_id] = round(relevance, 6)
        if q.get("leader_weight") is not None:
            raw_weights[question_id] = float(q["leader_weight"]) / leader_scale
            sources[question_id] = "leader"
        else:
            raw_weights[question_id] = relevance / topic_counts[topic_key(q)]
            sources[question_id] = "model_relevance" if "semantic_relevance" in q else "auto_relevance"

    total = sum(raw_weights.values())
    if soft and total <= 0:
        # With no relevant known option facts, a question's importance cannot
        # be inferred. Keep the unresolved comparisons visible to the matcher.
        raw_weights = {q["question_id"]: 1.0 for q in soft}
        sources = {q["question_id"]: "no_relevance_fallback" for q in soft}
        total = float(len(soft))

    return [
        {
            "question_id": q["question_id"],
            "label": q["label"],
            "kind": q["kind"],
            "weight": round(raw_weights[q["question_id"]] / total, 12) if q["question_id"] in raw_weights else None,
            "weight_source": sources.get(q["question_id"]),
            "relevance": relevances.get(q["question_id"], q.get("semantic_relevance") if q["kind"] == "semantic_requirement" else None),
            "aggregation": "average" if q["kind"] in {"open_preference", "semantic_preference"} else "direct",
            "is_hard_constraint": q["kind"] not in SOFT_KINDS,
        }
        for q in questions
    ]
