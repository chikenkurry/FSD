"""Contract validation and ranking regressions for the activity/time service."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from decision_service.algorithm import run_decision
from decision_service.contract import DEFAULT_OBJECTIVE, MISSING_VALUE_POLICY, ranking_order
from decision_service.preprocessing import preprocess


FIXTURES = Path(__file__).parent.parent / "fixtures" / "preprocessing"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def rating(member: str, activity: str, value: int) -> dict:
    return {"participant_id": member, "kind": "rating", "activity_id": activity,
            "rating": value, "source_question_id": "q_rating", "scope": "activity",
            "utility_rule": "rating_v1", "status": "confirmed", "source_type": "member_response",
            "source_answer_id": f"{member}-rating", "evidence": str(value)}


def algorithm_input() -> dict:
    candidates = []
    for aid, cost, indoor in (("a", 2000, "yes"), ("b", 1500, "no")):
        candidates.append({"candidate_id": aid, "activity_id": aid, "currency": "SGD",
                           "start_at": "2026-10-02T11:00:00Z", "end_at": "2026-10-02T13:00:00Z",
                           "estimated_cost_minor": cost,
                           "facts": [{"attribute_id": "indoor", "value": indoor, "value_type": "category",
                                      "unit": None, "status": "confirmed", "source": "venue"},
                                     {"attribute_id": "estimated_cost", "value": cost, "value_type": "integer",
                                      "unit": "SGD_minor", "status": "confirmed", "source": "quote"}]})
    return {
        "context": {"schema_version": "activity-v2", "activity_ids": ["a", "b"],
                    "algorithm_version": "baseline-v2", "policy_version": "test-v1"},
        "criteria": [{"attribute_id": "indoor", "value_type": "category", "unit": None},
                     {"attribute_id": "step_free_access", "value_type": "category", "unit": None},
                     {"attribute_id": "estimated_cost", "value_type": "integer", "unit": "SGD_minor"}],
        "candidates": candidates,
        "participants": [{"participant_id": "p1", "response_status": "complete", "is_required_for_decision": True}],
        "constraints": [{"participant_id": "p1",
                         "availability": {"available_intervals": [{"start_at": "2026-10-02T10:00:00Z", "end_at": "2026-10-02T14:00:00Z"}]},
                         "budget": {"kind": "limited", "max_cost_minor": 2000, "currency": "SGD"},
                         "required_attributes": [], "candidate_flags": []}],
        "preferences": [rating("p1", "a", 4), rating("p1", "b", 2)],
        "scoring_model": {
            "questions": [{"question_id": "q_rating", "weight": 1.0, "utility_rule": "rating_v1",
                           "aggregation": "direct", "missing_value_policy": "unresolved", "is_hard_constraint": False, "criteria": []},
                          {"question_id": "q_access", "weight": None, "utility_rule": None,
                           "is_hard_constraint": True, "criteria": ["step_free_access"]}],
            "group_objective": dict(DEFAULT_OBJECTIVE),
            "ranking_policy": {"feasibility_policy": "all_required_participants", "sort_order": ranking_order(DEFAULT_OBJECTIVE)},
            "missing_value_policy": dict(MISSING_VALUE_POLICY),
        },
    }


def attribute_preference(member: str, aid: str, value: str) -> dict:
    return {"participant_id": member, "source_question_id": "q_rating", "kind": "attribute_preference",
            "attribute_id": aid, "preferred_value": value, "utility_rule": "attribute_match_v1", "scope": "all",
            "status": "confirmed", "source_answer_id": "p1-pref", "source_type": "member_response", "evidence": value}


def use_attributes(data: dict) -> None:
    question = data["scoring_model"]["questions"][0]
    question.update(utility_rule="attribute_match_v1", aggregation="average", criteria=["indoor", "step_free_access"])
    data["preferences"] = [attribute_preference("p1", "indoor", "yes")]


class AlgorithmTests(unittest.TestCase):
    def test_ranks_feasible_candidates_and_returns_pareto_frontier(self):
        result = run_decision(algorithm_input(), run_id="test-run")
        self.assertEqual(result.status.value, "ranked")
        self.assertEqual([item.candidate_id for item in result.ranked_candidates], ["a", "b"])
        self.assertEqual({item.candidate_id for item in result.pareto_frontier}, {"a", "b"})

    def test_hard_budget_and_time_constraints_exclude_candidate(self):
        data = algorithm_input()
        data["candidates"][0]["estimated_cost_minor"] = 2001
        data["candidates"][0]["facts"][1]["value"] = 2001
        data["candidates"][1].update(start_at="2026-10-02T15:00:00Z", end_at="2026-10-02T17:00:00Z")
        result = run_decision(data)
        self.assertEqual(result.status.value, "no_feasible_candidate")
        by_id = {item.candidate_id: item for item in result.candidate_results}
        self.assertIn("BUDGET_CONFLICT", by_id["a"].explanation_codes)
        self.assertIn("NO_TIME_OVERLAP", by_id["b"].explanation_codes)

    def test_unknown_required_fact_blocks(self):
        data = algorithm_input()
        requirement = {"participant_id": "p1", "attribute_id": "step_free_access", "required_value": "yes",
                       "source_question_id": "q_access", "source_answer_id": "p1-access", "source_type": "member_response",
                       "evidence": "I require step-free access", "status": "confirmed", "confirmation_status": "confirmed"}
        data["constraints"][0]["required_attributes"] = [requirement]
        result = run_decision(data)
        self.assertEqual(result.status.value, "blocked")
        self.assertTrue(all(item.feasibility.value == "unresolved" for item in result.candidate_results))
        requirement["confirmation_status"] = "needs_confirmation"
        self.assertEqual(run_decision(data).status.value, "invalid_input")

    def test_incomplete_required_participant_blocks_before_matching(self):
        data = algorithm_input()
        data["participants"][0]["response_status"] = "incomplete"
        result = run_decision(data)
        self.assertEqual(result.status.value, "blocked")
        self.assertIn("INCOMPLETE_RESPONSE", result.issues)

    def test_structured_preprocessing_fixture_can_be_consumed(self):
        processed = preprocess(fixture("planning_snapshot.json"), fixture("response_snapshot.json"))
        self.assertEqual(processed["status"], "ready")
        result = run_decision(processed["algorithm_input"])
        self.assertEqual(result.status.value, "ranked")
        self.assertTrue(result.ranked_candidates)

    def test_semantic_requirements_and_preferences_change_execution(self):
        planning = fixture("planning_semantic.json")
        responses = fixture("response_semantic.json")
        # Allow both prices so accessibility alone must exclude dinner.
        responses["participants"][0]["answers"][1]["value"]["max_cost_minor"] = 5000
        processed = preprocess(planning, responses, semantic_evidence=fixture("semantic_evidence.json"))
        self.assertEqual(processed["status"], "ready")
        result = run_decision(processed["algorithm_input"])
        self.assertEqual([c.candidate_id for c in result.ranked_candidates], ["cafe@2026-10-02T11:00:00Z"])
        self.assertEqual(result.ranked_candidates[0].min_member_score, 1.0)
        self.assertIn("REQUIRED_ATTRIBUTE_NOT_MET", result.candidate_results[1].explanation_codes)
        serialized = json.dumps(result.as_dict())
        self.assertNotIn("I need a ramp", serialized)
        self.assertNotIn("source_answer_id", serialized)

    def test_group_policy_changes_the_winner(self):
        data = algorithm_input()
        data["participants"].append({"participant_id": "p2", "response_status": "complete", "is_required_for_decision": True})
        second_constraint = copy.deepcopy(data["constraints"][0])
        second_constraint["participant_id"] = "p2"
        data["constraints"].append(second_constraint)
        data["preferences"] = [rating("p1", "a", 4), rating("p2", "a", 1), rating("p1", "b", 2), rating("p2", "b", 2)]
        self.assertEqual(run_decision(data).ranked_candidates[0].candidate_id, "b")
        objective = {"mode": "weighted_fairness", "minimum_score_weight": 0.0, "average_score_weight": 1.0, "fairness_weight": 0.0}
        data["scoring_model"].update(group_objective=objective)
        data["scoring_model"]["ranking_policy"]["sort_order"] = ranking_order(objective)
        self.assertEqual(run_decision(data).ranked_candidates[0].candidate_id, "a")
        objective["fairness_weight"] = 1.0
        result = run_decision(data)
        self.assertEqual(result.ranked_candidates[0].candidate_id, "b")
        self.assertEqual(result.ranked_candidates[0].fairness_penalty, 0)

    def test_default_objective_preserves_maximin_ranking(self):
        result = run_decision(algorithm_input())
        self.assertEqual(result.ranked_candidates[0].group_score, result.ranked_candidates[0].min_member_score)

    def test_unknown_soft_fact_blocks_the_whole_recommendation(self):
        data = algorithm_input()
        use_attributes(data)
        data["candidates"][0]["facts"][0].update(value=None, status="unknown")
        result = run_decision(data)
        self.assertEqual(result.status.value, "blocked")
        self.assertEqual(result.ranked_candidates, ())
        self.assertIn("MISSING_SOFT_OPTION_FACT", result.candidate_results[0].explanation_codes)
        self.assertEqual(result.candidate_results[1].feasibility.value, "feasible")

    def test_indifference_is_neutral_and_missing_answer_is_unresolved(self):
        data = algorithm_input()
        preference = data["preferences"][0]
        preference.pop("rating")
        preference.update(kind="indifferent", utility_rule="neutral_v1", status="explicitly_indifferent")
        self.assertEqual(run_decision(data).ranked_candidates[0].min_member_score, 0.5)
        data["preferences"].remove(preference)
        self.assertEqual(run_decision(data).status.value, "blocked")

    def test_average_aggregation_shares_the_question_weight(self):
        data = algorithm_input()
        use_attributes(data)
        data["preferences"].append(attribute_preference("p1", "step_free_access", "yes"))
        for candidate in data["candidates"]:
            candidate["facts"].append({"attribute_id": "step_free_access", "value": "no", "value_type": "category",
                                       "unit": None, "status": "confirmed", "source": "venue"})
        self.assertEqual(run_decision(data).ranked_candidates[0].min_member_score, 0.5)
        data["scoring_model"]["questions"][0]["aggregation"] = "direct"
        self.assertEqual(run_decision(data).status.value, "invalid_input")

    def test_candidate_and_scenario_scope_apply_only_to_their_target(self):
        for scope in ("candidate", "scenario"):
            with self.subTest(scope=scope):
                data = algorithm_input()
                for candidate in data["candidates"]:
                    candidate["scenario_id"] = "scenario-" + candidate["candidate_id"]
                for preference in data["preferences"]:
                    activity = preference.pop("activity_id")
                    preference.update(scope=scope)
                    preference[f"{scope}_id"] = activity if scope == "candidate" else "scenario-" + activity
                result = run_decision(data)
                self.assertEqual(result.status.value, "ranked")
                self.assertEqual(result.ranked_candidates[0].min_member_score, 1)
                self.assertEqual(result.ranked_candidates[1].min_member_score, 0.5)

    def test_unknown_and_estimated_costs_do_not_pass_hard_budget(self):
        for status, value, code in (("unknown", None, "MISSING_COST"), ("estimated", 2000, "ESTIMATED_COST")):
            with self.subTest(status=status):
                data = algorithm_input()
                candidate = data["candidates"][0]
                candidate["estimated_cost_minor"] = value
                candidate["facts"][1].update(value=value, status=status)
                result = run_decision(data)
                self.assertEqual(result.status.value, "blocked")
                self.assertIn(code, result.candidate_results[0].explanation_codes)

    def test_duplicate_rows_are_rejected(self):
        for field, nested in (("participants", None), ("constraints", None), ("candidates", None),
                              ("questions", "scoring_model"), ("preferences", None), ("criteria", None)):
            with self.subTest(field=field):
                data = algorithm_input()
                container = data[nested] if nested else data
                container[field].append(copy.deepcopy(container[field][0]))
                self.assertEqual(run_decision(data).status.value, "invalid_input")

    def test_invalid_weights_rules_and_units_are_rejected(self):
        for value in (float("nan"), float("inf"), -1, True, 0.8, 10 ** 500):
            with self.subTest(weight=value):
                data = algorithm_input()
                data["scoring_model"]["questions"][0]["weight"] = value
                self.assertEqual(run_decision(data).status.value, "invalid_input")
        for field, value in (("utility_rule", "invented_v1"), ("missing_value_policy", "neutral")):
            data = algorithm_input()
            data["scoring_model"]["questions"][0][field] = value
            self.assertEqual(run_decision(data).status.value, "invalid_input")
        data = algorithm_input()
        data["candidates"][0]["facts"][1]["unit"] = "USD_minor"
        self.assertEqual(run_decision(data).status.value, "invalid_input")

    def test_malformed_types_and_naive_timestamps_are_rejected(self):
        for field, value in (("context", []), ("candidates", [None]), ("participants", "p1"),
                             ("constraints", None), ("preferences", [{}]), ("scoring_model", [])):
            with self.subTest(field=field):
                data = algorithm_input()
                data[field] = value
                self.assertEqual(run_decision(data).status.value, "invalid_input")
        data = algorithm_input()
        data["candidates"][0]["start_at"] = "2026-10-02T11:00:00"
        self.assertEqual(run_decision(data).status.value, "invalid_input")

    def test_ranking_policy_cannot_silently_disagree_with_objective(self):
        data = algorithm_input()
        data["scoring_model"]["ranking_policy"]["sort_order"] = ["lowest_estimated_cost"]
        self.assertEqual(run_decision(data).status.value, "invalid_input")

    def test_nested_malformed_values_return_invalid_input(self):
        paths = [
            ("scoring_model", "group_objective", "mode"),
            ("scoring_model", "questions", 0, "utility_rule"),
            ("scoring_model", "questions", 0, "aggregation"),
            ("participants", 0, "response_status"),
            ("candidates", 0, "facts", 0, "status"),
            ("candidates", 0, "facts", 0, "value_type"),
            ("preferences", 0, "participant_id"),
            ("preferences", 0, "scope"),
            ("preferences", 0, "kind"),
            ("preferences", 0, "activity_id"),
            ("constraints", 0, "budget", "kind"),
        ]
        for path in paths:
            for value in (None, [], {}, False, 42):
                with self.subTest(path=path, value=value):
                    data = algorithm_input()
                    target = data
                    for part in path[:-1]:
                        target = target[part]
                    target[path[-1]] = value
                    self.assertEqual(run_decision(data).status.value, "invalid_input")

    def test_zero_weight_question_does_not_require_option_evidence(self):
        data = algorithm_input()
        use_attributes(data)
        question = data["scoring_model"]["questions"][0]
        question["weight"] = 0
        data["scoring_model"]["questions"].append({
            "question_id": "q_neutral", "weight": 1, "utility_rule": "neutral_v1", "aggregation": "direct",
            "missing_value_policy": "unresolved", "is_hard_constraint": False, "criteria": [],
        })
        data["preferences"][0]["attribute_id"] = "step_free_access"
        data["preferences"].append({
            "participant_id": "p1", "source_question_id": "q_neutral", "source_answer_id": "p1-neutral",
            "kind": "indifferent", "utility_rule": "neutral_v1", "scope": "all", "status": "explicitly_indifferent",
            "source_type": "member_response", "evidence": "Anything is fine",
        })
        result = run_decision(data)
        self.assertEqual(result.status.value, "ranked")
        self.assertEqual(result.ranked_candidates[0].min_member_score, 0.5)

    def test_sparse_schema_is_blocked_before_activity_validation(self):
        for schema in ("sparse-v2", "sparse-v3"):
            with self.subTest(schema=schema):
                result = run_decision({"context": {"schema_version": schema}, "candidates": [{"option_id": "x"}]})
                self.assertEqual(result.status.value, "blocked")
                self.assertEqual(result.issues, ("SPARSE_HANDOFF_NOT_SUPPORTED",))

    def test_empty_candidate_inventory_returns_no_feasible_candidate(self):
        data = algorithm_input()
        data["candidates"] = []
        self.assertEqual(run_decision(data).status.value, "no_feasible_candidate")


if __name__ == "__main__":
    unittest.main()
