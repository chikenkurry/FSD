from __future__ import annotations

import unittest

from decision_service.adapters import adapt_generic_to_option_v1, adapt_scenarios_to_option_v1
from decision_service.generic_algorithm import run_decision


def preparation() -> dict:
    return {
        "status": "ready",
        "context": {"policy_version": "test-policy-v1"},
        "criteria": [{"attribute_id": "keyboard", "value_type": "category", "unit": None},
                     {"attribute_id": "portable", "value_type": "boolean", "unit": None}],
        "candidates": [
            {"option_id": "a", "facts": [
                {"attribute_id": "keyboard", "value_type": "category", "value": "quiet", "status": "confirmed"},
                {"attribute_id": "portable", "value_type": "boolean", "value": True, "status": "confirmed"},
            ]},
            {"option_id": "b", "facts": [
                {"attribute_id": "keyboard", "value_type": "category", "value": "clicky", "status": "confirmed"},
                {"attribute_id": "portable", "value_type": "boolean", "value": True, "status": "confirmed"},
            ]},
        ],
        "participants": [
            {"participant_id": "p1", "is_required_for_decision": True},
            {"participant_id": "p2", "is_required_for_decision": True},
        ],
        "constraints": [{"participant_id": "p1", "source_question_id": "q_portable", "attribute_id": "portable",
                         "kind": "attribute_requirement", "required_value": True, "constraint_rule": "equals_v1", "status": "confirmed"}],
        "preferences": [
            {"participant_id": "p1", "source_question_id": "q_keyboard", "attribute_id": "keyboard", "kind": "attribute_preference",
             "preferred_value": "quiet", "utility_rule": "attribute_match_v1", "polarity": "prefer"},
            {"participant_id": "p2", "source_question_id": "q_keyboard", "attribute_id": "keyboard", "kind": "attribute_preference",
             "preferred_value": "clicky", "utility_rule": "attribute_match_v1", "polarity": "prefer"},
        ],
        "scoring_model": {
            "questions": [
                {"question_id": "q_portable", "role": "hard"},
                {"question_id": "q_keyboard", "role": "soft", "weight": 1.0},
            ],
            "member_weights": [
                {"participant_id": "p1", "source_question_id": "q_keyboard", "attribute_id": "keyboard", "effective_weight": 1.0, "status": "resolved"},
                {"participant_id": "p2", "source_question_id": "q_keyboard", "attribute_id": "keyboard", "effective_weight": 1.0, "status": "resolved"},
            ],
            "group_objective": {"mode": "maximin_then_average", "minimum_score_weight": 0.5, "average_score_weight": 0.5, "fairness_weight": 0.0},
        },
    }


class GenericOptionV1Tests(unittest.TestCase):
    def handoff(self, source: dict | None = None) -> dict:
        result = adapt_generic_to_option_v1(source or preparation())
        self.assertEqual(result["status"], "ready")
        return result["algorithm_input"]

    def test_adapter_and_runner_rank_a_ready_packet(self):
        result = run_decision(self.handoff())
        self.assertEqual(result.status, "ranked")
        self.assertEqual([row["option_id"] for row in result.ranked_candidates], ["a", "b"])
        self.assertEqual(result.ranked_candidates[0]["min_member_score"], 0.0)
        self.assertEqual({row["option_id"] for row in result.pareto_frontier}, {"a", "b"})

    def test_hard_constraint_excludes_a_candidate(self):
        source = preparation()
        source["candidates"][1]["facts"][1]["value"] = False
        result = run_decision(self.handoff(source))
        self.assertEqual([row["option_id"] for row in result.ranked_candidates], ["a"])
        by_id = {row["option_id"]: row for row in result.candidate_results}
        self.assertEqual(by_id["b"]["feasibility"], "infeasible")

    def test_unknown_soft_fact_blocks_ranking(self):
        source = preparation()
        source["candidates"][0]["facts"][0]["status"] = "unknown"
        source["candidates"][1]["facts"][0]["status"] = "unknown"
        result = run_decision(self.handoff(source))
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.candidate_results[0]["explanation_codes"], ["MISSING_SOFT_OPTION_FACT"])

    def test_explicit_indifference_scores_without_an_option_fact(self):
        source = preparation()
        source["preferences"][0].update(kind="indifferent", utility_rule="neutral_v1")
        source["candidates"][0]["facts"][0]["status"] = "unknown"
        result = run_decision(self.handoff(source))
        self.assertEqual(result.status, "ranked")  # p2 can still evaluate option b.
        source["preferences"][1].update(kind="indifferent", utility_rule="neutral_v1")
        source["candidates"][1]["facts"][0]["status"] = "unknown"
        result = run_decision(self.handoff(source))
        self.assertEqual(result.status, "ranked")
        self.assertEqual(result.ranked_candidates[0]["min_member_score"], 0.5)

    def test_adapter_accepts_numeric_rules(self):
        source = preparation()
        source["criteria"][0]["value_type"] = "number"
        source["preferences"][0]["utility_rule"] = "numeric_target_v1"
        result = adapt_generic_to_option_v1(source)
        self.assertEqual(result["status"], "ready")

    def test_adapter_does_not_silently_drop_an_unresolved_member_weight(self):
        source = preparation()
        source["scoring_model"]["member_weights"][0]["status"] = "unresolved"
        source["scoring_model"]["member_weights"][0]["effective_weight"] = None
        result = adapt_generic_to_option_v1(source)
        self.assertEqual(result["status"], "unsupported")
        self.assertIn("UNRESOLVED_MEMBER_WEIGHTS", [issue["code"] for issue in result["issues"]])

    def test_weighted_fairness_uses_the_same_member_scores(self):
        source = preparation()
        source["scoring_model"]["group_objective"] = {"mode": "weighted_fairness", "minimum_score_weight": 0.0,
                                                         "average_score_weight": 1.0, "fairness_weight": 0.0}
        result = run_decision(self.handoff(source))
        self.assertEqual(result.ranked_candidates[0]["average_member_score"], 0.5)

    def test_avoidance_preference_inverts_category_utility(self):
        source = preparation()
        source["preferences"][0].update(preferred_value="clicky", polarity="avoid")
        source["preferences"][1].update(kind="indifferent", utility_rule="neutral_v1")
        result = run_decision(self.handoff(source))
        self.assertEqual(result.ranked_candidates[0]["option_id"], "a")
        self.assertEqual(result.ranked_candidates[0]["min_member_score"], 0.5)

    def test_numeric_hard_limit_and_target_utility(self):
        source = preparation()
        source["criteria"] = [{"attribute_id": "price", "value_type": "number", "unit": "USD"}]
        source["candidates"] = [
            {"option_id": "a", "facts": [{"attribute_id": "price", "value_type": "number", "value": 90, "status": "confirmed"}]},
            {"option_id": "b", "facts": [{"attribute_id": "price", "value_type": "number", "value": 110, "status": "confirmed"}]},
            {"option_id": "c", "facts": [{"attribute_id": "price", "value_type": "number", "value": 140, "status": "confirmed"}]},
        ]
        source["constraints"] = [{"participant_id": "p1", "source_question_id": "q_price", "attribute_id": "price",
                                  "kind": "attribute_requirement", "required_value": 120, "constraint_rule": "maximum_v1", "status": "confirmed"}]
        source["preferences"] = [
            {"participant_id": participant, "source_question_id": "q_price", "attribute_id": "price", "kind": "attribute_preference",
             "preferred_value": 100, "utility_rule": "numeric_target_v1", "utility_parameters": {"scale": 20}, "polarity": "prefer"}
            for participant in ("p1", "p2")
        ]
        source["scoring_model"]["questions"] = [{"question_id": "q_price", "role": "hard"}, {"question_id": "q_price", "role": "soft", "weight": 1.0}]
        source["scoring_model"]["member_weights"] = [
            {"participant_id": participant, "source_question_id": "q_price", "attribute_id": "price", "effective_weight": 1.0, "status": "resolved"}
            for participant in ("p1", "p2")
        ]
        result = run_decision(self.handoff(source))
        self.assertEqual([row["option_id"] for row in result.ranked_candidates], ["a", "b"])
        by_id = {row["option_id"]: row for row in result.candidate_results}
        self.assertEqual(by_id["c"]["feasibility"], "infeasible")

    def test_tag_set_hard_rules_and_overlap_preferences(self):
        source = preparation()
        source["criteria"] = [{"attribute_id": "features", "value_type": "tag_set", "unit": None}]
        source["candidates"] = [
            {"option_id": "a", "facts": [{"attribute_id": "features", "value_type": "tag_set", "value": ["usb", "quiet"], "status": "confirmed"}]},
            {"option_id": "b", "facts": [{"attribute_id": "features", "value_type": "tag_set", "value": ["usb", "loud"], "status": "confirmed"}]},
            {"option_id": "c", "facts": [{"attribute_id": "features", "value_type": "tag_set", "value": ["quiet"], "status": "confirmed"}]},
        ]
        source["constraints"] = [{"participant_id": "p1", "source_question_id": "q_features", "attribute_id": "features",
                                  "kind": "attribute_requirement", "required_value": ["usb"], "constraint_rule": "contains_all_v1", "status": "confirmed"}]
        source["preferences"] = [
            {"participant_id": "p1", "source_question_id": "q_features", "attribute_id": "features", "kind": "attribute_preference",
             "preferred_value": ["quiet"], "utility_rule": "tag_overlap_v1", "polarity": "prefer"},
            {"participant_id": "p2", "source_question_id": "q_features", "attribute_id": "features", "kind": "attribute_preference",
             "preferred_value": ["loud"], "utility_rule": "tag_overlap_v1", "polarity": "avoid"},
        ]
        source["scoring_model"]["questions"] = [{"question_id": "q_features", "role": "soft", "weight": 1.0}]
        source["scoring_model"]["member_weights"] = [
            {"participant_id": participant, "source_question_id": "q_features", "attribute_id": "features", "effective_weight": 1.0, "status": "resolved"}
            for participant in ("p1", "p2")
        ]
        result = run_decision(self.handoff(source))
        self.assertEqual([row["option_id"] for row in result.ranked_candidates], ["a", "b"])
        self.assertEqual(next(row for row in result.candidate_results if row["option_id"] == "c")["feasibility"], "infeasible")

    def test_scenario_adapter_materializes_confirmed_cost_and_duration(self):
        source = preparation()
        source["criteria"] += [
            {"attribute_id": "duration_days", "value_type": "number", "unit": "days"},
            {"attribute_id": "max_cost", "value_type": "decimal", "unit": "SGD"},
        ]
        source["preferences"] = [
            {"participant_id": participant, "source_question_id": "q_duration", "attribute_id": "duration_days", "kind": "attribute_preference",
             "preferred_value": 3, "utility_rule": "numeric_target_v1", "utility_parameters": {"scale": 2}, "polarity": "prefer"}
            for participant in ("p1", "p2")
        ]
        source["scoring_model"]["questions"] = [{"question_id": "q_duration", "role": "soft", "weight": 1.0}]
        source["scoring_model"]["member_weights"] = [
            {"participant_id": participant, "source_question_id": "q_duration", "attribute_id": "duration_days", "effective_weight": 1.0, "status": "resolved"}
            for participant in ("p1", "p2")
        ]
        source["scenario_requests"] = [
            {"option_id": "a", "duration_days": 3, "earliest_start_date": "2027-06-01", "latest_start_date": "2027-06-03",
             "cost_evidence_status": "confirmed", "cost_evidence": {"amount": "500", "status": "confirmed", "source": "quote"}},
            {"option_id": "b", "duration_days": 4, "earliest_start_date": "2027-06-01", "latest_start_date": "2027-06-02",
             "cost_evidence_status": "confirmed", "cost_evidence": {"amount": "500", "status": "confirmed", "source": "quote"}},
        ]
        adapted = adapt_scenarios_to_option_v1(source)
        self.assertEqual(adapted["status"], "ready")
        handoff = adapted["algorithm_input"]
        self.assertEqual(handoff["candidates"][0]["scenario"]["duration_days"], 3)
        self.assertEqual(run_decision(handoff).ranked_candidates[0]["option_id"].split("@")[0], "a")


if __name__ == "__main__":
    unittest.main()
