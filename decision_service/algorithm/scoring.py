"""Apply declared utilities after feasibility; missing evidence has no score."""

from __future__ import annotations

from typing import Any

from decision_service.contract import applies, candidate_fact

from .models import CandidateScore


class UnresolvedScore(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def group_objective_metrics(minimum: float, average: float, scores: dict[str, float], policy: dict[str, Any]) -> tuple[float, float]:
    """Population variance measures disagreement among required members."""
    variance = sum((value - average) ** 2 for value in scores.values()) / len(scores)
    if policy["mode"] == "maximin_then_average":
        return minimum, variance
    minimum_weight = policy["minimum_score_weight"]
    average_weight = policy["average_score_weight"]
    total = minimum_weight + average_weight
    base = minimum_weight / total * minimum + average_weight / total * average
    return base - policy["fairness_weight"] * variance, variance


def _rating(preference: dict, candidate: dict) -> float:
    return preference["rating"] / 4


def _neutral(preference: dict, candidate: dict) -> float:
    return 0.5


def _attribute_match(preference: dict, candidate: dict) -> float:
    fact = candidate_fact(candidate, preference["attribute_id"])
    if fact is None or fact["status"] == "unknown":
        raise UnresolvedScore("MISSING_SOFT_OPTION_FACT")
    return 1.0 if fact["value"] == preference["preferred_value"] else 0.0


UTILITIES = {"rating_v1": _rating, "attribute_match_v1": _attribute_match, "neutral_v1": _neutral}


def score_candidate(
    candidate: dict,
    participants: list[dict],
    preferences: list[dict],
    questions: list[dict],
    objective: dict,
) -> CandidateScore:
    active_questions = [q for q in questions if not q["is_hard_constraint"] and q["weight"] > 0]
    grouped = {}
    for preference in preferences:
        if applies(preference, candidate):
            key = (preference["participant_id"], preference["source_question_id"])
            grouped.setdefault(key, []).append(preference)
    scores = {}
    for participant in participants:
        if not participant["is_required_for_decision"]:
            continue
        member_id = participant["participant_id"]
        total = 0.0
        for question in active_questions:
            answers = grouped.get((member_id, question["question_id"]), [])
            if not answers:
                raise UnresolvedScore("MISSING_SOFT_ANSWER")
            fits = [UTILITIES[answer["utility_rule"]](answer, candidate) for answer in answers]
            utility = fits[0] if question["aggregation"] == "direct" else sum(fits) / len(fits)
            total += question["weight"] * utility
        scores[member_id] = round(total, 12)
    minimum = min(scores.values())
    average = sum(scores.values()) / len(scores)
    group_score, fairness_penalty = group_objective_metrics(minimum, average, scores, objective)
    return CandidateScore(candidate, minimum, average, group_score, fairness_penalty)
