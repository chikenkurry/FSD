"""Normalization boundaries and policy propagation across both services."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from decision_service.algorithm import run_decision
from decision_service.contract import validate_handoff
from decision_service.preprocessing import preprocess


FIXTURES = Path(__file__).parent.parent / "fixtures" / "preprocessing"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.planning = fixture("planning_semantic.json")
        self.responses = fixture("response_semantic.json")
        self.evidence = fixture("semantic_evidence.json")

    def process(self, policy=None):
        return preprocess(self.planning, self.responses, policy=policy, semantic_evidence=self.evidence)

    def test_model_requirement_needs_confirmation_of_the_actual_value(self):
        answer = self.responses["participants"][0]["answers"][3]
        for confirmation in (None, {"attribute_id": "step_free_access", "required_value": "no"},
                             {"attribute_id": "indoor", "required_value": "yes"}):
            with self.subTest(confirmation=confirmation):
                answer["confirmed_requirement"] = confirmation
                result = self.process()
                self.assertEqual(result["status"], "needs_clarification")
                self.assertIn("CONFIRM_REQUIREMENT", [i["code"] for i in result["issues"]])
                self.assertIsNone(result["algorithm_input"])
                self.assertEqual(result["semantic_evidence"], self.evidence)

    def test_unmapped_model_meaning_cannot_be_executed(self):
        self.evidence["answer_assessments"]["p1"]["q_travel"]["value"] = "invented"
        result = self.process()
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("UNMAPPED_SEMANTIC_VALUE", [i["code"] for i in result["issues"]])
        self.assertIsNone(result["algorithm_input"])

    def test_generic_model_question_without_a_binding_is_provisional(self):
        self.planning["questions"][2].pop("semantic_binding")
        result = self.process()
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIsNone(result["algorithm_input"])

    def test_dynamic_category_criterion_is_not_a_travel_special_case(self):
        question = self.planning["questions"][2]
        question["label"] = "What noise level do you prefer?"
        question["choices"][0]["label"] = "Quiet"
        question["semantic_binding"] = {"attribute_id": "noise_level", "value_type": "category", "values": {"quiet": "quiet"}}
        for activity in self.planning["activities"]:
            activity["attributes"] = [a for a in activity["attributes"] if a["attribute_id"] != "walkable"]
            activity["attributes"].append({"attribute_id": "noise_level", "value_type": "category",
                                           "value": "quiet", "source": "venue_information", "status": "confirmed"})
        for member in self.evidence["answer_assessments"].values():
            member["q_travel"].update(value="quiet", criterion="noise_level", evidence="Quiet", meaning="Prefers quiet venues")
        result = self.process()
        self.assertEqual(result["status"], "ready")
        validate_handoff(result["algorithm_input"])
        preference = result["algorithm_input"]["preferences"][0]
        self.assertEqual((preference["attribute_id"], preference["preferred_value"]), ("noise_level", "quiet"))
        self.assertEqual(run_decision(result["algorithm_input"]).ranked_candidates[0].min_member_score, 1)

    def test_boolean_and_numeric_bindings_preserve_type_and_unit(self):
        for kind, value, unit in (("boolean", True, None), ("integer", 2, "count"), ("number", 2.5, "hours")):
            with self.subTest(kind=kind):
                self.setUp()
                self.planning["questions"][2]["semantic_binding"] = {
                    "attribute_id": "custom_feature", "value_type": kind, "unit": unit, "values": {"walkable": value}}
                for activity in self.planning["activities"]:
                    activity["attributes"] = [a for a in activity["attributes"] if a["attribute_id"] != "walkable"]
                    activity["attributes"].append({"attribute_id": "custom_feature", "value_type": kind, "value": value, "unit": unit})
                result = self.process()
                self.assertEqual(result["status"], "ready")
                self.assertEqual(run_decision(result["algorithm_input"]).ranked_candidates[0].min_member_score, 1)

    def test_malformed_and_conflicting_fact_types_are_rejected(self):
        attribute = self.planning["activities"][0]["attributes"][1]
        attribute.update(value_type="integer", value="yes")
        self.assertEqual(self.process()["status"], "invalid_input")
        attribute["value"] = 1
        result = self.process()
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["issues"][0]["code"], "CONFLICTING_FACT_TYPE")

    def test_group_policy_is_frozen_in_the_validated_handoff(self):
        objective = {"mode": "weighted_fairness", "minimum_score_weight": 0.2,
                     "average_score_weight": 0.8, "fairness_weight": 1.0}
        result = self.process({"group_objective": objective})
        self.assertEqual(result["status"], "ready")
        model = result["algorithm_input"]["scoring_model"]
        self.assertEqual(model["group_objective"], objective)
        self.assertEqual(model["ranking_policy"]["sort_order"][0], "highest_group_score")
        self.assertEqual(run_decision(result["algorithm_input"]).status.value, "ranked")
        objective["fairness_weight"] = float("inf")
        self.assertEqual(self.process({"group_objective": objective})["status"], "invalid_input")

    def test_fact_sources_and_answer_provenance_survive_normalization(self):
        result = self.process()
        preference = result["algorithm_input"]["preferences"][0]
        self.assertEqual((preference["source_answer_id"], preference["source_question_id"], preference["source_type"], preference["evidence"]),
                         ("p1-a3", "q_travel", "semantic_model", "Walkable"))
        fact = result["algorithm_input"]["candidates"][0]["facts"][0]
        self.assertEqual((fact["status"], fact["source"]), ("confirmed", "planning_service"))

    def test_numeric_hard_confirmation_must_include_the_unit(self):
        self.planning["questions"][3]["semantic_binding"] = {
            "attribute_id": "access_width", "value_type": "integer", "unit": "cm", "values": {"ramp_required": 90}}
        answer = self.responses["participants"][0]["answers"][3]
        answer["confirmed_requirement"] = {"attribute_id": "access_width", "required_value": 90}
        result = self.process()
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("CONFIRM_REQUIREMENT", [i["code"] for i in result["issues"]])

    def test_confirmation_cannot_substitute_integer_for_boolean(self):
        self.planning["questions"][3]["semantic_binding"] = {
            "attribute_id": "accessible", "value_type": "boolean", "values": {"ramp_required": True}}
        self.responses["participants"][0]["answers"][3]["confirmed_requirement"] = {
            "attribute_id": "accessible", "required_value": 1}
        result = self.process()
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("CONFIRM_REQUIREMENT", [i["code"] for i in result["issues"]])


if __name__ == "__main__":
    unittest.main()
