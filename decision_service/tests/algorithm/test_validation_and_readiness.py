from dataclasses import replace

from app.algorithm import (
    BudgetConstraint,
    ExplanationCode,
    Participant,
    Status,
    run_decision_algorithm,
)

from .fixtures import project_plan_fixture


def test_blocks_incomplete_required_participant() -> None:
    input_data = project_plan_fixture()
    participants = (
        replace(input_data.participants[0], response_status="incomplete"),
        *input_data.participants[1:],
    )
    output = run_decision_algorithm(replace(input_data, participants=participants))

    assert output.status == Status.BLOCKED
    assert ExplanationCode.INCOMPLETE_RESPONSE in output.explanation_codes


def test_optional_incomplete_participant_does_not_block() -> None:
    input_data = project_plan_fixture()
    participants = (
        Participant(
            participant_id="optional",
            response_status="incomplete",
            is_required_for_decision=False,
        ),
        *input_data.participants,
    )
    output = run_decision_algorithm(replace(input_data, participants=participants))

    assert output.status == Status.RANKED


def test_blocks_invalid_duplicate_candidate_ids() -> None:
    input_data = project_plan_fixture()
    duplicate = replace(input_data.candidates[1], candidate_id=input_data.candidates[0].candidate_id)
    output = run_decision_algorithm(
        replace(input_data, candidates=(input_data.candidates[0], duplicate))
    )

    assert output.status == Status.BLOCKED
    assert ExplanationCode.INVALID_INPUT in output.explanation_codes


def test_blocks_duplicate_constraints_for_same_participant() -> None:
    input_data = project_plan_fixture()
    output = run_decision_algorithm(
        replace(
            input_data,
            constraints=(input_data.constraints[0], input_data.constraints[0]),
        )
    )

    assert output.status == Status.BLOCKED
    assert ExplanationCode.INVALID_INPUT in output.explanation_codes


def test_blocks_unknown_participant_status() -> None:
    input_data = project_plan_fixture()
    participants = (
        replace(input_data.participants[0], response_status="mystery"),
        *input_data.participants[1:],
    )
    output = run_decision_algorithm(replace(input_data, participants=participants))

    assert output.status == Status.BLOCKED
    assert ExplanationCode.INVALID_INPUT in output.explanation_codes


def test_blocks_limited_budget_without_cap() -> None:
    input_data = project_plan_fixture()
    constraints = (
        replace(input_data.constraints[0], budget=BudgetConstraint(kind="limited")),
        *input_data.constraints[1:],
    )
    output = run_decision_algorithm(replace(input_data, constraints=constraints))

    assert output.status == Status.BLOCKED
    assert ExplanationCode.INVALID_INPUT in output.explanation_codes


def test_blocks_unresolved_candidates_instead_of_calling_them_infeasible() -> None:
    input_data = project_plan_fixture()
    candidates = (replace(input_data.candidates[0], estimated_cost_minor=None),)
    preferences = tuple(
        preference
        for preference in input_data.preferences
        if preference.activity_id == "board_game_cafe"
    )
    output = run_decision_algorithm(
        replace(input_data, candidates=candidates, preferences=preferences)
    )

    assert output.status == Status.BLOCKED
    assert ExplanationCode.MISSING_COST in output.explanation_codes
