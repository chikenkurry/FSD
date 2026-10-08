from __future__ import annotations

from decision_service.adapters import adapt_generic_to_activity_v2
from decision_service.algorithm import run_decision


def _preparation() -> dict:
    return {
        "status": "ready",
        "context": {"round_id": "round-1", "option_snapshot_id": "options-1", "response_snapshot_id": "responses-1"},
        "criteria": [
            {"attribute_id": "estimated_cost", "value_type": "integer", "unit": "SGD_minor"},
            {"attribute_id": "indoor", "value_type": "category", "unit": None},
        ],
        "candidates": [
            {"option_id": "cafe", "facts": [
                {"attribute_id": "estimated_cost", "value": 2000, "value_type": "integer", "unit": "SGD_minor", "status": "confirmed", "source": "menu"},
                {"attribute_id": "indoor", "value": "yes", "value_type": "category", "unit": None, "status": "confirmed", "source": "venue"},
            ]},
        ],
        "participants": [{"participant_id": "p1", "response_status": "complete", "is_required_for_decision": True}],
        "constraints": [{
            "participant_id": "p1", "attribute_id": "max_cost", "required_value": 2500,
            "constraint_rule": "maximum_v1", "status": "confirmed",
        }],
        "preferences": [{
            "participant_id": "p1", "source_question_id": "q_indoor", "source_answer_id": "a1",
            "source_type": "member_response", "evidence": "indoors", "kind": "attribute_preference",
            "attribute_id": "indoor", "preferred_value": "yes", "utility_rule": "attribute_match_v1",
            "scope": "all", "status": "confirmed", "polarity": "prefer",
        }],
        "scoring_model": {
            "group_objective": {"mode": "maximin_then_average", "minimum_score_weight": 0.6, "average_score_weight": 0.4, "fairness_weight": 0.0},
            "questions": [{"question_id": "q_indoor", "role": "soft", "weight": 1.0, "utility_rule": "attribute_match_v1", "aggregation": "direct", "criteria": ["indoor"]}],
        },
    }


def _execution_context() -> dict:
    return {
        "candidates": [{
            "option_id": "cafe", "candidate_id": "cafe@2026-10-02T11:00:00Z", "activity_id": "cafe",
            "start_at": "2026-10-02T11:00:00Z", "end_at": "2026-10-02T13:00:00Z", "currency": "SGD",
        }],
        "availability_by_participant": {"p1": [{"start_at": "2026-10-02T10:00:00Z", "end_at": "2026-10-02T14:00:00Z"}]},
    }


def test_adapts_a_compatible_preparation_and_runs_activity_algorithm() -> None:
    adapted = adapt_generic_to_activity_v2(_preparation(), _execution_context())

    assert adapted["status"] == "ready"
    result = run_decision(adapted["algorithm_input"])
    assert result.status.value == "ranked"
    assert result.ranked_candidates[0].candidate_id.startswith("cafe@")


def test_requires_concrete_candidates_and_availability() -> None:
    adapted = adapt_generic_to_activity_v2(_preparation(), {})

    assert adapted["status"] == "needs_information"
    assert adapted["issues"][0]["code"] == "CONCRETE_CANDIDATES_REQUIRED"


def test_rejects_generic_avoidance_until_generic_algorithm_exists() -> None:
    preparation = _preparation()
    preparation["preferences"][0]["polarity"] = "avoid"

    adapted = adapt_generic_to_activity_v2(preparation, _execution_context())

    assert adapted["status"] == "unsupported"
    assert adapted["issues"][0]["code"] == "UNSUPPORTED_PREFERENCE"
