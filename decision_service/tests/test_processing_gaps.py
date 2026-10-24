"""Regression cases for requirement compatibility and explicit numeric intent."""

import copy
import unittest

from decision_service.preprocessing import preprocess
from decision_service.tests.test_preference_semantics import snapshots


class ProcessingGapTests(unittest.TestCase):
    def setUp(self):
        self.planning, self.responses = snapshots(
            [("capacity", "number", "kg"), ("features", "tag_set", None)],
            [{"capacity": 10, "features": ["cooling", "stackable"]},
             {"capacity": 20, "features": ["cooling"]}],
            {"question_id": "needs", "label": "Capacity preference?", "role": "soft", "criterion": "capacity", "relevance": 1})

    def answer(self, value):
        self.responses["participants"][0]["answers"][0]["value"] = value

    def process(self, **kwargs):
        return preprocess(self.planning, self.responses, **kwargs)

    def meanings(self, *items):
        self.answer({"preferences": list(items)})

    def hard(self, criterion, value, **kwargs):
        return {"criterion": criterion, "value": value, "must_have": True, **kwargs}

    def test_required_and_excluded_tag_overlap_requests_review(self):
        self.meanings(self.hard("features", ["Cooling"]),
                      self.hard("features", ["cooling"], polarity="avoid"))
        result = self.process()
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["preparation"]["status"], "needs_clarification")
        self.assertTrue(all(c["status"] == "needs_clarification" for c in result["preparation"]["constraints"]))
        conflict = next(i for i in result["issues"] if i["code"] == "CONFLICTING_ANSWER")
        self.assertIn("cooling", conflict["message"])
        self.assertIn("needs", conflict["message"])

    def test_tag_conflict_across_questions_uses_declared_aliases(self):
        self.planning["canonicalization"] = {"values": {"features": {"cooling": ["chilling"]}}}
        self.planning["questions"].append({"question_id": "avoid", "label": "Features preference?",
                                           "role": "soft", "criterion": "features", "relevance": 1})
        self.meanings(self.hard("features", ["chilling"]))
        self.responses["participants"][0]["answers"].append({"question_id": "avoid", "value": {
            "preferences": [self.hard("features", ["cooling"], polarity="avoid")]}})
        self.assertEqual(self.process()["status"], "needs_clarification")

    def test_multiple_required_sets_are_compatible(self):
        self.planning["questions"] = [{"question_id": q, "label": "Required features?", "role": "hard", "criterion": "features"}
                                       for q in ("needs", "more")]
        self.answer(["cooling"])
        self.responses["participants"][0]["answers"].append({"question_id": "more", "value": ["stackable"]})
        packet = self.process()["preparation"]
        self.assertEqual(packet["status"], "ready")
        self.assertEqual(len(packet["constraints"]), 2)

    def test_nonoverlapping_required_and_excluded_tags_are_compatible(self):
        self.meanings(self.hard("features", ["cooling"]), self.hard("features", ["fragile"], polarity="avoid"))
        self.assertEqual(self.process()["preparation"]["status"], "ready")

    def test_requirements_are_scoped_to_each_member(self):
        self.meanings(self.hard("features", ["cooling"]))
        second = copy.deepcopy(self.responses["participants"][0])
        second["participant_id"] = "p2"
        second["answers"][0]["value"]["preferences"][0]["polarity"] = "avoid"
        self.planning["roster"].append("p2")
        self.responses["participants"].append(second)
        # Group feasibility belongs to execution; neither member contradicted themself.
        self.assertNotIn("CONFLICTING_ANSWER", [i["code"] for i in self.process()["issues"]])

    def two_limits(self, lower, upper):
        self.planning["questions"] = [{"question_id": q, "label": "Capacity limit?", "role": "hard",
                                       "criterion": "capacity", "numeric_intent": intent}
                                      for q, intent in (("needs", "minimum"), ("cap", "maximum"))]
        self.answer(lower)
        self.responses["participants"][0]["answers"].append({"question_id": "cap", "value": upper})

    def test_differing_upper_limits_preserve_both_sources(self):
        self.two_limits(18, 15)
        self.planning["questions"][0]["numeric_intent"] = "maximum"
        packet = self.process()["preparation"]
        self.assertEqual(packet["status"], "ready")
        self.assertEqual([(c["source_question_id"], c["required_value"]) for c in packet["constraints"]], [("needs", 18), ("cap", 15)])

    def test_inclusive_touching_bounds_are_compatible_but_open_bounds_are_not(self):
        self.two_limits(15, 15)
        self.assertEqual(self.process()["preparation"]["status"], "ready")
        self.planning["questions"][1]["numeric_intent"] = "less_than"
        result = self.process()
        self.assertEqual(result["status"], "needs_clarification")
        self.assertTrue(all(c["status"] == "needs_clarification" for c in result["preparation"]["constraints"]))

    def test_incompatible_bounds_request_review(self):
        self.two_limits(16, 15)
        self.assertEqual(self.process()["status"], "needs_clarification")

    def test_compound_limits_intersect_within_one_answer(self):
        self.meanings(self.hard("capacity", 10, intent="minimum"), self.hard("capacity", 15, intent="maximum"))
        packet = self.process()["preparation"]
        self.assertEqual(packet["status"], "ready")
        c = packet["constraints"][0]
        self.assertEqual(c["constraint_rule"], "within_range_v1")
        self.assertEqual(c["required_value"], {"lower": 10, "upper": 15, "lower_inclusive": True, "upper_inclusive": True})

    def test_compound_incompatible_limits_do_not_emit_a_usable_constraint(self):
        self.meanings(self.hard("capacity", 16, intent="minimum"), self.hard("capacity", 15, intent="maximum"))
        result = self.process()
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["preparation"]["constraints"], [])

    def test_unresolved_compound_hard_direction_does_not_crash_or_emit_partial_limits(self):
        self.meanings(self.hard("capacity", 10, intent="minimum"),
                      self.hard("capacity", None, intent="maximize"))
        result = self.process()
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["preparation"]["constraints"], [])

    def test_model_canonicalized_bound_cannot_borrow_confirmation_from_another_bound(self):
        class Provider:
            model = "criterion-alias"
            def canonicalize_sparse_label(self, payload):
                return {"status": "equivalent", "target": "capacity", "reason": "Same capacity dimension"}
        self.meanings(self.hard("capacity", 10, intent="minimum"),
                      self.hard("payload_capacity", 15, intent="maximum"))
        packet = self.process(semantic_provider=Provider())["preparation"]
        self.assertEqual(packet["status"], "needs_clarification")
        c = packet["constraints"][0]
        self.assertEqual(c["source_type"], "semantic_model")
        self.assertEqual(c["confirmation_status"], "needs_confirmation")

    def test_unconfirmed_interpretations_remain_pending_without_a_confirmed_conflict(self):
        self.meanings(self.hard("features", ["cooling"]), self.hard("features", ["cooling"], polarity="avoid"))
        packet = self.process()["preparation"]
        from decision_service.preprocessing.generic_validation import validate_preparation
        for c in packet["constraints"]:
            c.update(confirmation_status="needs_confirmation", status="needs_confirmation")
        issues = []
        validate_preparation(packet, issues)
        self.assertEqual(issues, [])

    def test_scalar_equal_and_not_equal_requirements_request_review(self):
        self.planning, self.responses = snapshots([("mode", "category", None)],
                                                [{"mode": "indoor"}, {"mode": "outdoor"}],
                                                {"question_id": "needs", "label": "Mode preference?", "role": "soft", "criterion": "mode", "relevance": 1})
        self.meanings(self.hard("mode", "indoor"), self.hard("mode", "indoor", polarity="avoid"))
        self.assertEqual(self.process()["status"], "needs_clarification")

    def test_decimal_intersections_are_exact(self):
        self.planning, self.responses = snapshots([("max_cost", "decimal", "USD")],
                                                [{"max_cost": "0.1"}, {"max_cost": "0.3"}],
                                                {"question_id": "needs", "label": "Budget preference?", "role": "soft", "criterion": "max_cost"})
        self.meanings(self.hard("max_cost", "0.1000000000000000001", intent="minimum"),
                      self.hard("max_cost", "0.1", intent="maximum"))
        self.assertEqual(self.process()["status"], "needs_clarification")

    def test_bare_number_requests_intent_without_calling_a_model(self):
        class NoModel:
            def extract_sparse_answer(self, *args):
                raise AssertionError("A model cannot decide what a bare number means")
        for value in (12, "12 kg"):
            with self.subTest(value=value):
                self.answer(value)
                result = self.process(semantic_provider=NoModel())
                self.assertEqual(result["status"], "needs_clarification")
                self.assertEqual(result["preparation"]["preferences"], [])
                self.assertIn("AMBIGUOUS_NUMERIC_INTENT", [i["code"] for i in result["issues"]])

    def test_explicit_target_minimum_and_direction_remain_different(self):
        cases = [("ideally 12 kg", "target", "numeric_target_v1"),
                 ("at least 12 kg", "minimum", "numeric_range_v1"),
                 ("higher is better", "maximize", "numeric_maximize_v1")]
        for value, intent, rule in cases:
            with self.subTest(value=value):
                self.answer(value)
                packet = self.process()["preparation"]
                self.assertEqual(packet["status"], "ready")
                p = packet["preferences"][0]
                self.assertEqual((p["numeric_intent"], p["utility_rule"], p["intent_source"]), (intent, rule, "answer"))

    def test_question_minimum_is_soft_unless_declared_hard(self):
        self.planning["questions"][0]["numeric_intent"] = "minimum"
        self.answer(12)
        packet = self.process()["preparation"]
        self.assertEqual(packet["constraints"], [])
        self.assertEqual(packet["preferences"][0]["preferred_value"]["lower"], 12)
        self.planning["questions"][0].update(role="hard", relevance=0)
        packet = self.process()["preparation"]
        self.assertEqual(packet["constraints"][0]["constraint_rule"], "minimum_v1")

    def test_structured_intent_overrides_question_default(self):
        self.planning["questions"][0]["numeric_intent"] = "minimum"
        self.meanings({"criterion": "capacity", "value": 12, "intent": "target"})
        p = self.process()["preparation"]["preferences"][0]
        self.assertEqual((p["numeric_intent"], p["utility_rule"]), ("target", "numeric_target_v1"))

    def test_question_wording_can_declare_target(self):
        self.planning["questions"][0]["label"] = "Ideal capacity?"
        self.answer(12)
        packet = self.process()["preparation"]
        self.assertEqual(packet["scoring_model"]["questions"][0]["numeric_intent_source"], "question_wording")
        self.assertEqual(packet["preferences"][0]["intent_source"], "question")

    def test_invalid_intent_and_incompatible_mapping_are_rejected(self):
        self.answer(12)
        for intent, mapping in (("faster", None), ([], None), ("minimum", {"comparison_rule": "numeric_target_v1"})):
            with self.subTest(intent=intent):
                q = self.planning["questions"][0]
                q["numeric_intent"] = intent
                if mapping: q["mapping"] = mapping
                self.assertEqual(self.process()["status"], "invalid_input")

    def test_model_cannot_supply_intent_missing_from_a_compound_answer(self):
        class Provider:
            model = "invented-intent"
            def extract_sparse_answer(self, *args):
                return {"status": "resolved", "interpretations": [{"criterion": "capacity", "value": "12 kg",
                    "intent": "target", "evidence": "capacity 12 kg", "must_have": False, "polarity": "prefer"}]}
        self.planning["questions"][0].update(criterion="preferences", label="Any preferences?")
        self.answer("Capacity 12 kg and cooling please")
        result = self.process(semantic_provider=Provider())
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["preparation"]["preferences"], [])


if __name__ == "__main__":
    unittest.main()
