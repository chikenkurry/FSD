from __future__ import annotations

from typing import Any


def group_objective_metrics(minimum: float, average: float, scores: dict[str, float], policy: dict[str, Any]) -> tuple[float, float]:
    """Return (group score, fairness penalty) for a validated policy.

    The penalty is the population variance of member satisfaction. It is zero
    when every required participant has the same score.
    """
    values = list(scores.values())
    variance = sum((value - average) ** 2 for value in values) / len(values) if values else 0.0
    mode = policy.get("mode", "maximin_then_average")
    if mode == "maximin_then_average":
        return minimum, variance
    minimum_weight = float(policy.get("minimum_score_weight", 0.6))
    average_weight = float(policy.get("average_score_weight", 0.4))
    total = minimum_weight + average_weight
    base = (minimum_weight * minimum + average_weight * average) / total
    return base - float(policy.get("fairness_weight", 0.0)) * variance, variance


def score_candidate(candidate: dict[str, Any], participants: list[dict[str, Any]], preferences: list[dict[str, Any]], questions: list[dict[str, Any]], objective: dict[str, Any] | None = None) -> tuple[float, float, float, float, dict[str, float]]:
    weights = {q["question_id"]: q.get("weight") for q in questions}
    required = [p for p in participants if p.get("is_required_for_decision", True)]
    grouped: dict[str, list[dict[str, Any]]] = {p["participant_id"]: [] for p in required}
    for preference in preferences:
        if preference["participant_id"] in grouped:
            grouped[preference["participant_id"]].append(preference)
    scores: dict[str, float] = {}
    for participant in required:
        by_question: dict[str, list[float]] = {}
        for preference in grouped[participant["participant_id"]]:
            fit = _fit(preference, candidate)
            if fit is not None:
                by_question.setdefault(preference["source_question_id"], []).append(fit)
        total = 0.0
        for question_id, fits in by_question.items():
            weight = weights.get(question_id)
            if weight is not None:
                total += float(weight) * (sum(fits) / len(fits))
        scores[participant["participant_id"]] = round(total, 12)
    values = list(scores.values())
    minimum = min(values) if values else 0.0
    average = sum(values) / len(values) if values else 0.0
    group_score, fairness_penalty = group_objective_metrics(minimum, average, scores, objective or {})
    return minimum, average, group_score, fairness_penalty, scores


def _fit(preference: dict[str, Any], candidate: dict[str, Any]) -> float | None:
    if preference.get("kind") == "indifferent":
        return 0.5
    if preference.get("kind") == "rating":
        target = preference.get("candidate_id") or preference.get("activity_id")
        if target not in {candidate.get("candidate_id"), candidate.get("activity_id")}:
            return None
        return preference["rating"] / 4
    if preference.get("kind") == "attribute_preference":
        actual = next((a.get("value") for a in candidate.get("attributes", []) if a.get("attribute_id") == preference.get("attribute_id")), "unknown")
        if actual == "unknown":
            return None
        return 1.0 if actual == preference.get("preferred_value") else 0.0
    return None
