from __future__ import annotations

from datetime import datetime
from typing import Any


class AlgorithmInputError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AlgorithmInputError(message)


def validate_algorithm_input(data: dict[str, Any]) -> None:
    _require(isinstance(data, dict), "algorithm input must be an object")
    for key in ("context", "candidates", "participants", "constraints", "preferences", "scoring_model"):
        _require(key in data, f"missing algorithm input field: {key}")
    candidates = data["candidates"]
    participants = data["participants"]
    _require(isinstance(candidates, list) and candidates, "candidates must be a non-empty list")
    _require(isinstance(participants, list) and participants, "participants must be a non-empty list")
    candidate_ids = [c.get("candidate_id") for c in candidates]
    participant_ids = [p.get("participant_id") for p in participants]
    _require(all(isinstance(x, str) and x for x in candidate_ids), "every candidate needs an ID")
    _require(len(candidate_ids) == len(set(candidate_ids)), "candidate IDs must be unique")
    _require(len(participant_ids) == len(set(participant_ids)), "participant IDs must be unique")
    _require(any(p.get("is_required_for_decision", True) for p in participants), "at least one required participant is needed")
    known_candidates = set(candidate_ids)
    known_participants = set(participant_ids)
    for c in candidates:
        _require(c.get("start_at") and c.get("end_at"), f"candidate {c['candidate_id']} needs a time range")
        start = _parse_time(c["start_at"])
        end = _parse_time(c["end_at"])
        _require(end > start, f"candidate {c['candidate_id']} has an invalid time range")
        cost = c.get("estimated_cost_minor")
        _require(cost is None or isinstance(cost, int) and not isinstance(cost, bool) and cost >= 0, f"candidate {c['candidate_id']} has an invalid cost")
    for constraint in data["constraints"]:
        _require(constraint.get("participant_id") in known_participants, "constraint references an unknown participant")
        for flag in constraint.get("candidate_flags", []):
            _require(flag.get("candidate_id") in known_candidates, "candidate flag references an unknown candidate")
    for preference in data["preferences"]:
        _require(preference.get("participant_id") in known_participants, "preference references an unknown participant")
        if preference.get("candidate_id") is not None:
            _require(preference["candidate_id"] in known_candidates, "preference references an unknown candidate")
        rating = preference.get("rating")
        _require(rating is None or isinstance(rating, int) and not isinstance(rating, bool) and 0 <= rating <= 4, "rating must be an integer from 0 to 4")
    for question in data["scoring_model"].get("questions", []):
        weight = question.get("weight")
        if weight is not None:
            _require(isinstance(weight, (int, float)) and not isinstance(weight, bool) and weight >= 0, "question weights must be nonnegative")
    objective = data["scoring_model"].get("group_objective", {})
    _require(isinstance(objective, dict), "group_objective must be an object")
    _require(objective.get("mode", "maximin_then_average") in {"maximin_then_average", "weighted_fairness"}, "unsupported group objective mode")
    for name in ("minimum_score_weight", "average_score_weight", "fairness_weight"):
        value = objective.get(name, 0.0)
        _require(isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0, f"{name} must be nonnegative")
    if objective.get("mode", "maximin_then_average") == "weighted_fairness":
        _require(objective.get("minimum_score_weight", 0.6) + objective.get("average_score_weight", 0.4) > 0, "weighted fairness needs a positive score weight")


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise AlgorithmInputError(f"invalid timestamp: {value}") from exc
