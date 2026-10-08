"""Generic preprocessing: declared comparisons and grounded typed answers."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from decision_service.preprocessing import preprocess


FIXTURES = Path(__file__).parents[1] / "fixtures" / "preprocessing"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


class GenericPreprocessingTests(unittest.TestCase):
    def setUp(self):
        self.planning = fixture("planning_generic.json")
        self.responses = fixture("response_generic.json")

    def process(self, **kwargs):
        return preprocess(self.planning, self.responses, **kwargs)

    def declare_question_roles(self):
        for question, criterion in zip(self.planning["questions"], ("max_cost", "battery_life", "usage_tags")):
            question.update(role="hard" if criterion == "max_cost" else "soft", criterion=criterion,
                            relevance=0 if criterion == "max_cost" else 0.5)

    def test_generates_complete_typed_preparation_without_model_or_manual_bindings(self):
        result = self.process()
        self.assertEqual(result["preparation"]["status"], "ready")
        self.assertEqual(result["status"], "provisional")
        self.assertIsNone(result["algorithm_input"])
        packet = result["preparation"]
        self.assertEqual(packet["scenario_requests"], [])
        self.assertEqual(packet["fact_requests"], [])
        question = packet["scoring_model"]["questions"][1]
        self.assertEqual(question["mapping"]["comparison_rule"], "numeric_target_v1")
        self.assertEqual(question["mapping"]["parameters"], {"scale": 3.0})
        self.assertEqual(packet["preferences"][0]["preferred_value"], 12)
        self.assertEqual(packet["preferences"][1]["preferred_value"], ["coding", "design"])
        self.assertEqual(packet["constraints"][0]["required_value"], "1500")
        self.assertEqual(packet, fixture("expected_generic_preparation.json"))

    def test_weights_and_mappings_do_not_depend_on_member_answers(self):
        baseline = self.process()["preparation"]["scoring_model"]
        self.responses["participants"][0]["answers"][1]["value"] = 15
        self.responses["participants"][0]["answers"][2]["value"] = ["Presentations"]
        self.assertEqual(self.process()["preparation"]["scoring_model"], baseline)

    def test_option_names_do_not_create_missing_facts(self):
        self.planning["options"][0]["facts"].pop()
        result = self.process()
        self.assertEqual(result["preparation"]["status"], "needs_information")
        requests = result["preparation"]["fact_requests"]
        self.assertEqual(len(requests), 1)
        self.assertEqual((requests[0]["option_id"], requests[0]["attribute_id"], requests[0]["value_type"]),
                         ("device-a", "usage_tags", "tag_set"))
        self.assertEqual(len(result["preparation"]["candidates"][0]["facts"]), 2)

    def test_wrong_answer_unit_needs_clarification(self):
        self.responses["participants"][0]["answers"][1]["value"] = "12 minutes"
        result = self.process()
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("UNIT_MISMATCH", [i["code"] for i in result["issues"]])

    def test_inconsistent_option_fact_units_are_rejected(self):
        self.planning["options"][1]["facts"][1]["unit"] = "minutes"
        result = self.process()
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["issues"][0]["code"], "CONFLICTING_FACT_TYPE")

    def test_unknown_and_estimated_facts_request_confirmation(self):
        for status in ("unknown", "estimated"):
            with self.subTest(status=status):
                self.setUp()
                fact = self.planning["options"][0]["facts"][2]
                fact["status"] = status
                if status == "unknown":
                    fact.update(value=None, value_type="tag_set")
                result = self.process()
                self.assertEqual(result["preparation"]["status"], "needs_information")
                exported = result["preparation"]["candidates"][0]["facts"][2]
                self.assertEqual(exported["status"], status)
                self.assertTrue(result["preparation"]["fact_requests"])
                if status == "unknown":
                    self.assertIsNone(exported["value"])

    def test_optional_missing_answer_is_not_neutral(self):
        self.planning["questions"][2]["required"] = False
        self.responses["participants"][0]["answers"].pop()
        result = self.process()
        self.assertEqual(result["preparation"]["status"], "needs_clarification")
        self.assertIn("MISSING_ANSWER", [i["code"] for i in result["issues"]])

    def test_explicit_indifference_has_its_own_resolution_status(self):
        self.responses["participants"][0]["answers"][1]["value"] = "No preference"
        result = self.process()
        neutral = result["preparation"]["preferences"][0]
        self.assertEqual((neutral["kind"], neutral["status"], neutral["utility_rule"]),
                         ("indifferent", "explicitly_indifferent", "neutral_v1"))
        self.assertEqual(result["preparation"]["status"], "ready")

    def test_numeric_mapping_needs_declared_scale_when_facts_do_not_differ(self):
        self.planning["options"][1]["facts"][1]["value"] = 12
        result = self.process()
        self.assertIn("UNRESOLVED_QUESTION_MAPPING", [i["code"] for i in result["issues"]])
        self.planning["questions"][1]["mapping"] = {"value_type": "number", "unit": "hours",
                                                    "comparison_rule": "numeric_target_v1", "scale": 4}
        self.assertEqual(self.process()["preparation"]["status"], "ready")

    def test_boolean_question_normalizes_without_a_model(self):
        for option, value in zip(self.planning["options"], (True, False)):
            option["facts"].append({"criterion": "repairable", "value": value, "status": "confirmed", "source": "manufacturer"})
        self.planning["questions"].append({"question_id": "repair", "label": "Repairable preference?", "answer_format": "boolean"})
        self.responses["participants"][0]["answers"].append({"question_id": "repair", "value": True})
        result = self.process()
        value = result["preparation"]["preferences"][-1]
        self.assertEqual((value["value_type"], value["preferred_value"]), ("boolean", True))
        self.assertEqual(value["source_answer_id"], "product-responses-1:p1:repair")

    def test_duplicate_answer_ids_and_unsupported_rules_are_rejected(self):
        self.responses["participants"][0]["answers"][1]["answer_id"] = "p1-budget"
        self.assertEqual(self.process()["status"], "invalid_input")
        self.setUp()
        self.planning["questions"][1]["mapping"] = {"comparison_rule": "invented_v1"}
        self.assertEqual(self.process()["status"], "invalid_input")

    def test_budget_k_suffix_is_exact_and_does_not_use_country_names(self):
        self.responses["participants"][0]["answers"][0]["value"] = "USD 2k"
        result = self.process()
        self.assertEqual(result["preparation"]["constraints"][0]["required_value"], "2000")

    def test_group_policy_reaches_generic_preparation(self):
        objective = {"mode": "weighted_fairness", "fairness_weight": 0.5}
        result = self.process(policy={"group_objective": objective})
        policy = result["preparation"]["scoring_model"]["group_objective"]
        self.assertEqual((policy["mode"], policy["fairness_weight"]), ("weighted_fairness", 0.5))
        self.assertEqual(self.process(policy={"group_objective": {"fairness_weight": float("nan")}})["status"], "invalid_input")

    def test_unrecognized_wording_uses_model_with_fact_registry_and_replays(self):
        class Provider:
            model = "test-model"
            calls = []

            def classify_question(self, question, context):
                self.calls.append(copy.deepcopy(context))
                return {"role": "soft", "criterion": "battery_life", "relevance": 0.8,
                        "reason": "Member is being asked for desired runtime",
                        "mapping": {"value_type": "number", "unit": "hours", "comparison_rule": "numeric_target_v1", "scale": None}}

        self.planning["questions"] = [{"question_id": "battery", "label": "How long should it run unplugged?", "numeric_intent": "target"}]
        self.responses["participants"][0]["answers"] = [{"answer_id": "runtime", "question_id": "battery", "value": 12}]
        provider = Provider()
        original = self.process(semantic_provider=provider)
        self.assertEqual(original["preparation"]["status"], "ready")
        self.assertIn("criteria", provider.calls[0])
        self.assertNotIn("participants", provider.calls[0])
        self.assertEqual(self.process(semantic_evidence=original["semantic_evidence"]), original)

    def test_model_cannot_invent_numeric_scale_or_change_fact_unit(self):
        class Provider:
            model = "bad-model"

            def classify_question(self, question, context):
                return {"role": "soft", "criterion": "battery_life", "relevance": 0.8, "reason": "Runtime",
                        "mapping": self.mapping}

        provider = Provider()
        self.planning["questions"] = [{"question_id": "battery", "label": "How long should it run unplugged?", "numeric_intent": "target"}]
        self.responses["participants"][0]["answers"] = [{"question_id": "battery", "value": 12}]
        for mapping in ({"scale": 100}, {"value_type": "number", "unit": "minutes"}):
            with self.subTest(mapping=mapping):
                provider.mapping = mapping
                packet = self.process(semantic_provider=provider)["preparation"]
                self.assertEqual(packet["status"], "ready")
                self.assertEqual(packet["scoring_model"]["questions"][0]["mapping"]["unit"], "hours")
                self.assertEqual(packet["scoring_model"]["questions"][0]["mapping"]["parameters"], {"scale": 3.0})

    def test_live_provider_does_not_override_supported_rules_or_query_known_facts(self):
        class Provider:
            model = "should-not-be-called"

            def classify_question(self, *args):
                raise AssertionError("Structured questions must use supported rules")

            extract_sparse_answer = classify_question
            suggest_option_tags = classify_question

        result = self.process(semantic_provider=Provider())
        self.assertEqual(result["preparation"], self.process()["preparation"])

    def test_model_nonsoft_relevance_is_derived_as_zero(self):
        class Provider:
            model = "ceiling-provider"

            def classify_question(self, question, context):
                return {"role": "hard", "criterion": "max_cost", "relevance": 0.8, "reason": "Spending ceiling"}

        self.planning["questions"] = [{"question_id": "budget", "label": "What is your spending ceiling?"}]
        self.responses["participants"][0]["answers"] = [{"question_id": "budget", "value": 1500}]
        result = self.process(semantic_provider=Provider())
        question = result["preparation"]["scoring_model"]["questions"][0]
        self.assertEqual((question["relevance"], question["weight"]), (0, None))
        self.assertEqual(result["preparation"]["status"], "ready")

    def test_model_cannot_make_a_numeric_target_hard_without_limit_wording(self):
        class Provider:
            model = "runtime-provider"

            def classify_question(self, question, context):
                return {"role": "hard", "criterion": "battery_life", "relevance": 1, "reason": "Runtime"}

            def extract_sparse_answer(self, *args):
                raise AssertionError("A numeric target should be parsed directly")

        self.planning["questions"] = [{"question_id": "runtime", "label": "How long should it run unplugged?", "numeric_intent": "target"}]
        self.responses["participants"][0]["answers"] = [{"question_id": "runtime", "value": "12 hours"}]
        packet = self.process(semantic_provider=Provider())["preparation"]
        self.assertEqual(packet["status"], "ready")
        self.assertEqual(packet["constraints"], [])
        self.assertEqual(packet["preferences"][0]["preferred_value"], 12)
        self.assertEqual(packet["scoring_model"]["questions"][0]["role"], "soft")

    def test_explicit_numeric_minimum_stays_hard_when_classified_by_model(self):
        class Provider:
            model = "minimum-provider"

            def classify_question(self, question, context):
                return {"role": "hard", "criterion": "battery_life", "relevance": 1, "reason": "Explicit minimum"}

        self.planning["questions"] = [{"question_id": "runtime", "label": "Minimum unplugged runtime required?"}]
        self.responses["participants"][0]["answers"] = [{"question_id": "runtime", "value": "12 hours"}]
        packet = self.process(semantic_provider=Provider())["preparation"]
        self.assertEqual(packet["constraints"][0]["constraint_rule"], "minimum_v1")
        self.assertEqual(packet["constraints"][0]["confirmation_status"], "needs_confirmation")

    def test_unrelated_must_clause_does_not_promote_a_preference_to_hard(self):
        class Provider:
            model = "broad-evidence-provider"

            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "interpretations": [
                    {"criterion": "usage_tags", "value": "coding", "evidence": answer_text, "must_have": True, "polarity": "prefer"},
                    {"criterion": "usage_tags", "value": "presentations", "evidence": answer_text, "must_have": True, "polarity": "avoid"},
                ]}

        self.declare_question_roles()
        self.planning["questions"][2].pop("choices")
        self.planning["questions"][2]["answer_format"] = "text"
        answer = self.responses["participants"][0]["answers"][2]
        for separator in (". ", " but ", " and "):
            with self.subTest(separator=separator):
                answer["value"] = "I prefer coding" + separator + "I must not do presentations"
                result = self.process(semantic_provider=Provider())
                constraints = [c for c in result["preparation"]["constraints"] if c["source_question_id"] == "usage"]
                self.assertEqual(len(constraints), 1)
                self.assertEqual(constraints[0]["required_value"], ["presentations"])
                self.assertEqual(constraints[0]["evidence"], "I must not do presentations")
                self.assertEqual(constraints[0]["constraint_rule"], "excludes_all_v1")
                self.assertEqual(constraints[0]["confirmation_status"], "needs_confirmation")
                coding = next(p for p in result["preparation"]["preferences"] if p.get("preferred_value") == ["coding"])
                self.assertEqual(coding["evidence"], "I prefer coding")

    def test_each_merged_meaning_retains_its_grounded_excerpt(self):
        class Provider:
            model = "excerpt-provider"

            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "interpretations": [
                    {"criterion": "usage_tags", "value": value, "evidence": value, "must_have": False}
                    for value in ("coding", "design")
                ]}

        self.declare_question_roles()
        self.planning["questions"][2].pop("choices")
        self.planning["questions"][2]["answer_format"] = "text"
        self.responses["participants"][0]["answers"][2]["value"] = "I like coding and design"
        preference = self.process(semantic_provider=Provider())["preparation"]["preferences"][-1]
        self.assertEqual(preference["preferred_value"], ["coding", "design"])
        self.assertEqual(preference["evidence_excerpts"], ["coding", "design"])
        self.assertEqual(preference["evidence"], "coding")

    def test_unsupported_requirement_evidence_needs_clarification(self):
        class Provider:
            model = "unsupported-requirement-provider"

            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "interpretations": [
                    {"criterion": "usage_tags", "value": "coding", "evidence": "coding", "must_have": True},
                ]}

        self.declare_question_roles()
        self.planning["questions"][2].pop("choices")
        self.planning["questions"][2]["answer_format"] = "text"
        self.responses["participants"][0]["answers"][2]["value"] = "Maybe coding"
        result = self.process(semantic_provider=Provider())
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("AMBIGUOUS_ANSWER", [issue["code"] for issue in result["issues"]])
        self.assertFalse(any(c["source_question_id"] == "usage" for c in result["preparation"]["constraints"]))

    def test_ordinary_avoidance_and_optional_wording_are_soft(self):
        class Provider:
            model = "optional-provider"

            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "interpretations": [
                    {"criterion": "usage_tags", "value": "presentations", "evidence": answer_text,
                     "must_have": True, "polarity": "avoid"},
                ]}

        self.declare_question_roles()
        self.planning["questions"][2].pop("choices")
        self.planning["questions"][2]["answer_format"] = "text"
        for text in ("I avoid presentations.", "Presentations aren't required.", "I don't need presentations."):
            with self.subTest(text=text):
                self.responses["participants"][0]["answers"][2]["value"] = text
                packet = self.process(semantic_provider=Provider())["preparation"]
                self.assertEqual(packet["status"], "ready")
                self.assertFalse(any(c["source_question_id"] == "usage" for c in packet["constraints"]))
                self.assertEqual(packet["preferences"][-1]["polarity"], "avoid")

    def test_boolean_requirement_evidence_with_final_period_is_preserved(self):
        class Provider:
            model = "boolean-provider"

            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "interpretations": [
                    {"criterion": "repairable", "value": "true", "evidence": answer_text,
                     "must_have": True, "polarity": "prefer"},
                ]}

        for option in self.planning["options"]:
            option["facts"].append({"criterion": "repairable", "value": True, "status": "confirmed", "source": "supplier"})
        self.planning["questions"] = [{"question_id": "repair", "label": "Any preferences?", "role": "soft",
                                      "criterion": "repairable", "relevance": 1}]
        self.responses["participants"][0]["answers"] = [{"question_id": "repair", "value": "It needs to be repairable."}]
        packet = self.process(semantic_provider=Provider())["preparation"]
        self.assertEqual(packet["constraints"][0]["required_value"], True)
        self.assertEqual(packet["constraints"][0]["confirmation_status"], "needs_confirmation")
        self.assertEqual(packet["constraints"][0]["evidence"], "It needs to be repairable")

    def test_old_processing_evidence_is_rejected(self):
        result = self.process(semantic_evidence={"option_snapshot_id": self.planning["option_snapshot_id"],
            "response_snapshot_id": self.responses["response_snapshot_id"], "processing_version": "sparse-v3",
            "question_assessments": {}, "answer_assessments": {}})
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["issues"][0]["code"], "STALE_SEMANTIC_EVIDENCE")

    def test_positive_and_negative_open_preferences_stay_separate(self):
        class Provider:
            model = "polarity-model"

            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "interpretations": [
                    {"criterion": "usage_tags", "value": "coding", "evidence": "coding", "must_have": False, "polarity": "prefer"},
                    {"criterion": "usage_tags", "value": "presentations", "evidence": "avoid presentations", "must_have": False, "polarity": "avoid"},
                ]}

        self.declare_question_roles()
        self.planning["questions"][2].pop("choices")
        self.planning["questions"][2]["answer_format"] = "text"
        self.responses["participants"][0]["answers"][2]["value"] = "I like coding but avoid presentations"
        result = self.process(semantic_provider=Provider())
        preferences = [p for p in result["preparation"]["preferences"] if p["source_question_id"] == "usage"]
        self.assertEqual([(p["polarity"], p["preferred_value"]) for p in preferences],
                         [("prefer", ["coding"]), ("avoid", ["presentations"])])

    def test_model_hard_requirement_requires_exact_typed_confirmation(self):
        class Provider:
            model = "requirement-model"

            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "interpretations": [
                    {"criterion": "usage_tags", "value": "coding", "evidence": "must support coding", "must_have": True, "polarity": "prefer"},
                ]}

        self.declare_question_roles()
        self.planning["questions"][2].pop("choices")
        self.planning["questions"][2]["answer_format"] = "text"
        answer = self.responses["participants"][0]["answers"][2]
        answer["value"] = "It must support coding"
        original = self.process(semantic_provider=Provider())
        self.assertEqual(original["status"], "needs_clarification")
        requirement = original["preparation"]["constraints"][-1]
        self.assertEqual(requirement["confirmation_status"], "needs_confirmation")
        answer["confirmed_requirement"] = {"attribute_id": "usage_tags", "required_value": ["coding"],
                                           "constraint_rule": "contains_all_v1", "unit": None}
        confirmed = self.process(semantic_evidence=original["semantic_evidence"])
        self.assertEqual(confirmed["preparation"]["status"], "ready")
        self.assertEqual(confirmed["preparation"]["constraints"][-1]["confirmation_status"], "confirmed")

    def test_processing_does_not_mutate_supplied_snapshots(self):
        planning, responses = copy.deepcopy(self.planning), copy.deepcopy(self.responses)
        self.process()
        self.assertEqual(self.planning, planning)
        self.assertEqual(self.responses, responses)

    def test_unknown_cost_keeps_currency_and_scope_validation(self):
        fact = self.planning["options"][0]["facts"][0]
        fact.update(value=None, value_type="decimal", status="unknown")
        result = self.process()
        self.assertEqual(result["preparation"]["status"], "needs_information")
        fact["unit"] = "EUR"
        self.assertEqual(self.process()["status"], "invalid_input")

    def test_importance_question_is_not_assumed_to_be_a_numeric_target(self):
        self.planning["questions"][1]["label"] = "How important is battery life?"
        self.planning["questions"][1].pop("numeric_intent")
        result = self.process()
        question = result["preparation"]["scoring_model"]["questions"][1]
        self.assertEqual(question["role"], "importance")
        self.assertNotEqual(result["preparation"]["status"], "ready")

    def test_differing_budget_limits_are_compatible(self):
        self.planning["questions"].append({"question_id": "budget2", "label": "Maximum budget?"})
        self.responses["participants"][0]["answers"].append({"question_id": "budget2", "value": 1000})
        result = self.process()
        self.assertEqual(result["status"], "provisional")
        self.assertEqual(result["preparation"]["status"], "ready")
        self.assertEqual([c["required_value"] for c in result["preparation"]["constraints"]], ["1500", "1000"])
        self.assertNotIn("CONFLICTING_ANSWER", [i["code"] for i in result["issues"]])

    def test_malformed_question_mappings_return_errors(self):
        for mapping in ([1], {"comparison_rule": []}, {"value_type": {}}, {"unit": 12}, {"unexpected": True}):
            with self.subTest(mapping=mapping):
                self.planning["questions"][1]["mapping"] = mapping
                self.assertEqual(self.process()["status"], "invalid_input")

    def test_unknown_duration_wording_does_not_assume_travel_days(self):
        self.planning["questions"][1]["label"] = "How long should the warranty last?"
        self.planning["questions"][1].pop("numeric_intent")
        result = self.process()
        question = result["preparation"]["scoring_model"]["questions"][1]
        self.assertEqual(question["role"], "unclassified")
        self.assertNotEqual(question["criterion"], "duration_days")


if __name__ == "__main__":
    unittest.main()
