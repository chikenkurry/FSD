from __future__ import annotations

from .models import (
    BudgetConstraint,
    Candidate,
    CandidateResult,
    ExplanationCode,
    Feasibility,
    Participant,
    ParticipantConstraint,
    RequiredAttributeConstraint,
    TimeInterval,
)


HARD_FAILURES = {
    ExplanationCode.NO_TIME_OVERLAP,
    ExplanationCode.BUDGET_CONFLICT,
    ExplanationCode.REQUIRED_ATTRIBUTE_NOT_MET,
    ExplanationCode.CANNOT_JOIN,
}

UNRESOLVED_ISSUES = {
    ExplanationCode.MISSING_BUDGET,
    ExplanationCode.MISSING_COST,
    ExplanationCode.MISSING_OPTION_FACT,
    ExplanationCode.NEEDS_INFORMATION,
}


def evaluate_all_candidates(
    candidates: tuple[Candidate, ...],
    participants: tuple[Participant, ...],
    constraints: tuple[ParticipantConstraint, ...],
) -> tuple[CandidateResult, ...]:
    required_participants = tuple(
        participant for participant in participants if participant.is_required_for_decision
    )
    constraint_by_participant = {
        constraint.participant_id: constraint for constraint in constraints
    }

    return tuple(
        evaluate_candidate(candidate, required_participants, constraint_by_participant)
        for candidate in candidates
    )


def evaluate_candidate(
    candidate: Candidate,
    participants: tuple[Participant, ...],
    constraint_by_participant: dict[str, ParticipantConstraint],
) -> CandidateResult:
    codes: set[ExplanationCode] = set()

    for participant in participants:
        constraint = constraint_by_participant.get(participant.participant_id)
        if constraint is None:
            codes.add(ExplanationCode.INCOMPLETE_RESPONSE)
            continue

        codes.update(evaluate_participant_candidate(candidate, constraint))

    if codes & HARD_FAILURES:
        feasibility = Feasibility.INFEASIBLE
    elif codes & UNRESOLVED_ISSUES or ExplanationCode.INCOMPLETE_RESPONSE in codes:
        feasibility = Feasibility.UNRESOLVED
    else:
        feasibility = Feasibility.FEASIBLE

    return CandidateResult(
        candidate_id=candidate.candidate_id,
        feasibility=feasibility,
        explanation_codes=tuple(sorted(codes)),
    )


def evaluate_participant_candidate(
    candidate: Candidate,
    constraint: ParticipantConstraint,
) -> set[ExplanationCode]:
    codes: set[ExplanationCode] = set()

    if not check_availability(candidate, constraint.availability):
        codes.add(ExplanationCode.NO_TIME_OVERLAP)

    budget_code = check_budget(candidate, constraint.budget)
    if budget_code is not None:
        codes.add(budget_code)

    codes.update(check_required_attributes(candidate, constraint.required_attributes))
    codes.update(check_candidate_flags(candidate, constraint))

    return codes


def check_availability(candidate: Candidate, intervals: tuple[TimeInterval, ...]) -> bool:
    return any(
        interval.start_at <= candidate.start_at and candidate.end_at <= interval.end_at
        for interval in intervals
    )


def check_budget(
    candidate: Candidate,
    budget: BudgetConstraint,
) -> ExplanationCode | None:
    if budget.kind == "missing":
        return ExplanationCode.MISSING_BUDGET
    if budget.kind == "unlimited":
        return None
    if candidate.estimated_cost_minor is None:
        return ExplanationCode.MISSING_COST
    if budget.max_cost_minor is None:
        return ExplanationCode.MISSING_BUDGET
    if candidate.estimated_cost_minor > budget.max_cost_minor:
        return ExplanationCode.BUDGET_CONFLICT
    return None


def check_required_attributes(
    candidate: Candidate,
    required_attributes: tuple[RequiredAttributeConstraint, ...],
) -> set[ExplanationCode]:
    codes: set[ExplanationCode] = set()
    attributes = {
        attribute.attribute_id: attribute.value for attribute in candidate.attributes
    }

    for required in required_attributes:
        value = attributes.get(required.attribute_id)
        if value is None or value == "unknown":
            codes.add(ExplanationCode.MISSING_OPTION_FACT)
        elif value != required.required_value:
            codes.add(ExplanationCode.REQUIRED_ATTRIBUTE_NOT_MET)

    return codes


def check_candidate_flags(
    candidate: Candidate,
    constraint: ParticipantConstraint,
) -> set[ExplanationCode]:
    codes: set[ExplanationCode] = set()

    for flag in constraint.candidate_flags:
        if flag.candidate_id != candidate.candidate_id:
            continue
        if flag.flag == "cannot_join":
            codes.add(ExplanationCode.CANNOT_JOIN)
        elif flag.flag == "needs_information":
            codes.add(ExplanationCode.NEEDS_INFORMATION)

    return codes

