from __future__ import annotations

from dataclasses import dataclass

from .models import DecisionAlgorithmInput, ExplanationCode


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    explanation_codes: tuple[ExplanationCode, ...] = ()


def validate_input(input_data: DecisionAlgorithmInput) -> ValidationResult:
    candidate_ids = [candidate.candidate_id for candidate in input_data.candidates]
    participant_ids = [participant.participant_id for participant in input_data.participants]
    constraint_participant_ids = [
        constraint.participant_id for constraint in input_data.constraints
    ]

    if len(candidate_ids) != len(set(candidate_ids)):
        return _invalid()
    if len(participant_ids) != len(set(participant_ids)):
        return _invalid()
    if len(constraint_participant_ids) != len(set(constraint_participant_ids)):
        return _invalid()

    known_candidates = set(candidate_ids)
    known_activities = {candidate.activity_id for candidate in input_data.candidates}
    known_participants = set(participant_ids)
    required_participants = {
        participant.participant_id
        for participant in input_data.participants
        if participant.is_required_for_decision
    }

    if not required_participants:
        return _invalid()

    for candidate in input_data.candidates:
        if candidate.end_at <= candidate.start_at:
            return _invalid()
        if candidate.duration_minutes <= 0:
            return _invalid()
        if candidate.estimated_cost_minor is not None and candidate.estimated_cost_minor < 0:
            return _invalid()
        for attribute in candidate.attributes:
            if attribute.value not in {"yes", "no", "unknown"}:
                return _invalid()

    for participant in input_data.participants:
        if participant.response_status not in {
            "complete",
            "incomplete",
            "stale",
            "needs_clarification",
        }:
            return _invalid()

    if not required_participants.issubset(set(constraint_participant_ids)):
        return _invalid()

    for constraint in input_data.constraints:
        if constraint.participant_id not in known_participants:
            return _invalid()
        if constraint.budget.kind not in {"limited", "unlimited", "missing"}:
            return _invalid()
        if constraint.budget.max_cost_minor is not None and constraint.budget.max_cost_minor < 0:
            return _invalid()
        if constraint.budget.kind == "limited" and constraint.budget.max_cost_minor is None:
            return _invalid()
        for interval in constraint.availability:
            if interval.end_at <= interval.start_at:
                return _invalid()
        for flag in constraint.candidate_flags:
            if flag.candidate_id not in known_candidates:
                return _invalid()
            if flag.flag not in {"cannot_join", "needs_information"}:
                return _invalid()

    for preference in input_data.preferences:
        if preference.participant_id not in known_participants:
            return _invalid()
        if preference.rating < 0 or preference.rating > 4:
            return _invalid()
        if preference.candidate_id is None and preference.activity_id is None:
            return _invalid()
        if preference.candidate_id is not None and preference.candidate_id not in known_candidates:
            return _invalid()
        if preference.activity_id is not None and preference.activity_id not in known_activities:
            return _invalid()

    return ValidationResult(ok=True)


def _invalid() -> ValidationResult:
    return ValidationResult(ok=False, explanation_codes=(ExplanationCode.INVALID_INPUT,))
