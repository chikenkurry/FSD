from dataclasses import replace

from app.algorithm import (
    BudgetConstraint,
    CandidateAttribute,
    CandidateFlag,
    ExplanationCode,
    Feasibility,
    ParticipantConstraint,
    RequiredAttributeConstraint,
    TimeInterval,
)
from app.algorithm.feasibility import evaluate_candidate

from .fixtures import dt, project_plan_fixture


def test_availability_must_cover_full_duration() -> None:
    input_data = project_plan_fixture()
    candidate = input_data.candidates[0]
    participant = input_data.participants[0]
    constraint = ParticipantConstraint(
        participant_id=participant.participant_id,
        availability=(
            TimeInterval(
                start_at=dt("2026-10-02T19:00:00+08:00"),
                end_at=dt("2026-10-02T20:00:00+08:00"),
            ),
        ),
        budget=BudgetConstraint(kind="unlimited"),
    )

    result = evaluate_candidate(candidate, (participant,), {participant.participant_id: constraint})

    assert result.feasibility == Feasibility.INFEASIBLE
    assert ExplanationCode.NO_TIME_OVERLAP in result.explanation_codes


def test_budget_exact_equality_passes() -> None:
    input_data = project_plan_fixture()
    candidate = input_data.candidates[0]
    participant = input_data.participants[0]
    constraint = replace(
        input_data.constraints[0],
        budget=BudgetConstraint(kind="limited", max_cost_minor=2000, currency="SGD"),
    )

    result = evaluate_candidate(candidate, (participant,), {participant.participant_id: constraint})

    assert result.feasibility == Feasibility.FEASIBLE


def test_unknown_required_attribute_is_unresolved() -> None:
    input_data = project_plan_fixture()
    candidate = replace(
        input_data.candidates[0],
        attributes=(CandidateAttribute(attribute_id="step_free", value="unknown"),),
    )
    participant = input_data.participants[0]
    constraint = replace(
        input_data.constraints[0],
        required_attributes=(
            RequiredAttributeConstraint(attribute_id="step_free"),
        ),
    )

    result = evaluate_candidate(candidate, (participant,), {participant.participant_id: constraint})

    assert result.feasibility == Feasibility.UNRESOLVED
    assert ExplanationCode.MISSING_OPTION_FACT in result.explanation_codes


def test_candidate_flags_affect_feasibility() -> None:
    input_data = project_plan_fixture()
    candidate = input_data.candidates[0]
    participant = input_data.participants[0]
    constraint = replace(
        input_data.constraints[0],
        candidate_flags=(
            CandidateFlag(candidate_id=candidate.candidate_id, flag="cannot_join"),
        ),
    )

    result = evaluate_candidate(candidate, (participant,), {participant.participant_id: constraint})

    assert result.feasibility == Feasibility.INFEASIBLE
    assert ExplanationCode.CANNOT_JOIN in result.explanation_codes

