from dataclasses import replace

from app.algorithm import Status, run_decision_algorithm

from .fixtures import project_plan_fixture


def test_higher_min_rating_beats_higher_average_rating() -> None:
    input_data = project_plan_fixture()
    cheaper_picnic_same_time = replace(
        input_data.candidates[1],
        candidate_id="picnic_fri_1900",
        start_at=input_data.candidates[0].start_at,
        end_at=input_data.candidates[0].end_at,
    )
    input_data = replace(
        input_data,
        candidates=(input_data.candidates[0], cheaper_picnic_same_time),
        preferences=tuple(
            preference
            for preference in input_data.preferences
            if preference.activity_id in {"board_game_cafe", "picnic"}
        ),
    )

    output = run_decision_algorithm(input_data)

    assert output.status == Status.RANKED
    assert output.ranked_candidates[0].candidate_id == "picnic_fri_1900"
    assert output.ranked_candidates[1].candidate_id == "board_game_cafe_fri_1900"


def test_pareto_frontier_keeps_tradeoff_alternatives() -> None:
    input_data = project_plan_fixture()
    cheap_lower_average = replace(
        input_data.candidates[0],
        candidate_id="cheap_cafe_fri_1900",
        estimated_cost_minor=1000,
    )
    input_data = replace(
        input_data,
        candidates=(input_data.candidates[0], cheap_lower_average),
        preferences=tuple(
            preference
            for preference in input_data.preferences
            if preference.activity_id == "board_game_cafe"
        ),
    )

    output = run_decision_algorithm(input_data)
    pareto_ids = {candidate.candidate_id for candidate in output.pareto_candidates}

    assert pareto_ids == {"cheap_cafe_fri_1900"}
