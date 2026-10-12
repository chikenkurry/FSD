from app.algorithm import ExplanationCode, Feasibility, Status, run_decision_algorithm

from .fixtures import project_plan_fixture


def test_project_plan_fixture_selects_board_game_cafe() -> None:
    output = run_decision_algorithm(project_plan_fixture())

    assert output.status == Status.RANKED
    assert output.ranked_candidates[0].candidate_id == "board_game_cafe_fri_1900"
    assert output.ranked_candidates[0].average_preference_score == 79.2


def test_project_plan_fixture_explains_failed_candidates() -> None:
    output = run_decision_algorithm(project_plan_fixture())
    results = {result.candidate_id: result for result in output.candidate_results}

    assert results["picnic_sat_1400"].feasibility == Feasibility.INFEASIBLE
    assert ExplanationCode.NO_TIME_OVERLAP in results["picnic_sat_1400"].explanation_codes

    assert results["dinner_fri_1900"].feasibility == Feasibility.INFEASIBLE
    assert ExplanationCode.BUDGET_CONFLICT in results["dinner_fri_1900"].explanation_codes

