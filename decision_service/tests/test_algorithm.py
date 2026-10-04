from __future__ import annotations

import json
from pathlib import Path

from decision_service.algorithm import run_decision


ROOT = Path(__file__).parent.parent


def _input() -> dict:
    return {
        "context": {"algorithm_version": "baseline-v1", "policy_version": "test-v1"},
        "candidates": [
            {"candidate_id": "a", "activity_id": "a", "start_at": "2026-10-02T11:00:00Z", "end_at": "2026-10-02T13:00:00Z", "estimated_cost_minor": 2000, "attributes": [{"attribute_id": "indoor", "value": "yes"}]},
            {"candidate_id": "b", "activity_id": "b", "start_at": "2026-10-02T11:00:00Z", "end_at": "2026-10-02T13:00:00Z", "estimated_cost_minor": 1500, "attributes": [{"attribute_id": "indoor", "value": "no"}]},
        ],
        "participants": [{"participant_id": "p1", "response_status": "complete", "is_required_for_decision": True}],
        "constraints": [{
            "participant_id": "p1",
            "availability": {"available_intervals": [{"start_at": "2026-10-02T10:00:00Z", "end_at": "2026-10-02T14:00:00Z"}]},
            "budget": {"kind": "limited", "max_cost_minor": 2000},
            "required_attributes": [],
            "candidate_flags": [],
        }],
        "preferences": [
            {"participant_id": "p1", "kind": "rating", "activity_id": "a", "rating": 4, "source_question_id": "q_rating"},
            {"participant_id": "p1", "kind": "rating", "activity_id": "b", "rating": 2, "source_question_id": "q_rating"},
        ],
        "semantic_interpretations": [],
        "scoring_model": {"questions": [{"question_id": "q_rating", "weight": 1.0}]},
    }


def test_ranks_feasible_candidates_and_returns_pareto_frontier() -> None:
    result = run_decision(_input(), run_id="test-run")

    assert result.status.value == "ranked"
    assert [item.candidate_id for item in result.ranked_candidates] == ["a", "b"]
    assert {item.candidate_id for item in result.pareto_frontier} == {"a", "b"}


def test_hard_budget_and_time_constraints_exclude_candidate() -> None:
    data = _input()
    data["candidates"][0]["estimated_cost_minor"] = 2001
    data["candidates"][1]["start_at"] = "2026-10-02T15:00:00Z"
    data["candidates"][1]["end_at"] = "2026-10-02T17:00:00Z"

    result = run_decision(data)

    assert result.status.value == "no_feasible_candidate"
    by_id = {item.candidate_id: item for item in result.candidate_results}
    assert "BUDGET_CONFLICT" in by_id["a"].explanation_codes
    assert "NO_TIME_OVERLAP" in by_id["b"].explanation_codes


def test_unknown_required_fact_blocks_when_no_other_candidate_is_feasible() -> None:
    data = _input()
    data["constraints"][0]["required_attributes"] = [{"attribute_id": "step_free_access", "required_value": "yes"}]

    result = run_decision(data)

    assert result.status.value == "blocked"
    assert all(item.feasibility.value == "unresolved" for item in result.candidate_results)


def test_incomplete_required_participant_blocks_before_matching() -> None:
    data = _input()
    data["participants"][0]["response_status"] = "incomplete"

    result = run_decision(data)

    assert result.status.value == "blocked"
    assert "INCOMPLETE_RESPONSE" in result.issues


def test_structured_preprocessing_fixture_can_be_consumed() -> None:
    from decision_service.preprocessing.pipeline import preprocess

    planning = json.loads((ROOT / "fixtures" / "preprocessing" / "planning_snapshot.json").read_text(encoding="utf-8"))
    responses = json.loads((ROOT / "fixtures" / "preprocessing" / "response_snapshot.json").read_text(encoding="utf-8"))
    processed = preprocess(planning, responses)

    assert processed["status"] == "ready"
    result = run_decision(processed["algorithm_input"])
    assert result.status.value == "ranked"
    assert result.ranked_candidates


def test_weighted_fairness_objective_is_configurable() -> None:
    data = _input()
    data["participants"] = [
        {"participant_id": "p1", "response_status": "complete", "is_required_for_decision": True},
        {"participant_id": "p2", "response_status": "complete", "is_required_for_decision": True},
    ]
    data["constraints"].append({
        "participant_id": "p2",
        "availability": data["constraints"][0]["availability"],
        "budget": {"kind": "unlimited"},
        "required_attributes": [],
        "candidate_flags": [],
    })
    data["preferences"] += [
        {"participant_id": "p2", "kind": "rating", "activity_id": "a", "rating": 0, "source_question_id": "q_rating"},
        {"participant_id": "p2", "kind": "rating", "activity_id": "b", "rating": 4, "source_question_id": "q_rating"},
    ]
    data["scoring_model"]["group_objective"] = {
        "mode": "weighted_fairness",
        "minimum_score_weight": 0.2,
        "average_score_weight": 0.8,
        "fairness_weight": 1.0,
    }

    result = run_decision(data)

    assert result.status.value == "ranked"
    assert result.ranked_candidates[0].candidate_id == "b"
    assert result.ranked_candidates[0].fairness_penalty == 0.0625


def test_default_objective_preserves_maximin_ranking() -> None:
    result = run_decision(_input())

    assert result.ranked_candidates[0].group_score == result.ranked_candidates[0].min_member_score
