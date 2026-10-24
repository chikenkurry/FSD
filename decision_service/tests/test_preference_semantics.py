"""Compound meanings, numeric intent, and member importance across domains."""

from __future__ import annotations

import copy
import unittest

from decision_service.preprocessing import preprocess
from decision_service.preprocessing.common import InputError
from decision_service.preprocessing.generic_validation import validate_preparation


def snapshots(criteria, values, question=None):
    planning = {
        "round_id": "meaning-test", "option_revision": "1", "option_snapshot_id": "meaning-options",
        "decision_question": "Which option suits our group?", "roster": ["p1"],
        "currency": "USD", "cost_scope": "per_person_total",
        "options": [{"option_id": f"o{i}", "title": f"Option {i}", "facts": [
            {"criterion": aid, "value": row[aid], "value_type": kind, "status": "confirmed",
             "source": "test fixture", **({"unit": unit} if unit else {}),
             **({"context": {"scope": "per_person_total"}} if aid == "max_cost" else {})}
            for aid, kind, unit in criteria]} for i, row in enumerate(values)],
        "questions": [question or {"question_id": "preferences", "label": "Any personal preferences?",
                                   "role": "soft", "criterion": "preferences", "relevance": 1}],
    }
    responses = {"round_id": "meaning-test", "option_revision": "1", "response_snapshot_id": "meaning-responses",
                 "participants": [{"participant_id": "p1", "response_status": "complete",
                                   "answers": [{"question_id": planning["questions"][0]["question_id"], "value": None}]}]}
    return planning, responses


class PreferenceSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.planning, self.responses = snapshots(
            [("quiet", "boolean", None), ("max_cost", "decimal", "USD"), ("step_free_access", "boolean", None)],
            [{"quiet": True, "max_cost": "40", "step_free_access": True},
             {"quiet": False, "max_cost": "60", "step_free_access": False}])

    def answer(self, value):
        self.responses["participants"][0]["answers"][0]["value"] = value

    def process(self, **kwargs):
        result = preprocess(self.planning, self.responses, **kwargs)
        self.assertNotEqual(result["status"], "invalid_input", result.get("issues"))
        return result

    def numeric_question(self, kind="soft"):
        self.planning, self.responses = snapshots(
            [("battery_life", "number", "hours")], [{"battery_life": 10}, {"battery_life": 15}],
            {"question_id": "runtime", "label": "Battery life preference?", "role": kind,
             "criterion": "battery_life", "numeric_intent": "target" if kind == "soft" else "minimum",
             "relevance": 1 if kind == "soft" else 0})

    def test_one_structured_answer_can_have_three_criteria(self):
        self.answer({"preferences": [
            {"criterion": "quiet", "value": True},
            {"criterion": "max_cost", "value": "$50", "intent": "less_than", "must_have": True},
            {"criterion": "step_free_access", "value": True, "must_have": True}]})
        packet = self.process()["preparation"]
        self.assertEqual(packet["status"], "ready")
        self.assertEqual({c["attribute_id"]: c["constraint_rule"] for c in packet["constraints"]},
                         {"max_cost": "less_than_v1", "step_free_access": "equals_v1"})
        self.assertEqual({p["attribute_id"] for p in packet["preferences"]}, {"quiet", "step_free_access"})
        self.assertEqual([r["effective_weight"] for r in packet["scoring_model"]["member_weights"]], [0.5, 0.5])
        self.assertEqual(packet["fact_requests"], [])

    def test_compound_text_extracts_and_confirms_each_requirement_then_replays(self):
        class Provider:
            model = "compound-fixture"

            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "importance_relations": [], "interpretations": [
                    {"criterion": "quiet", "value": "true", "evidence": "I prefer somewhere quiet",
                     "must_have": False, "polarity": "prefer", "intent": "match"},
                    {"criterion": "max_cost", "value": "$50", "evidence": "I must spend under $50",
                     "must_have": True, "polarity": "prefer", "intent": "less_than"},
                    {"criterion": "step_free_access", "value": "true", "evidence": "I need step-free access",
                     "must_have": True, "polarity": "prefer", "intent": "match"}]}

        self.answer("I prefer somewhere quiet. I must spend under $50. I need step-free access.")
        original = self.process(semantic_provider=Provider())
        self.assertEqual(original["status"], "needs_clarification")
        requirements = original["preparation"]["constraints"]
        self.assertEqual(len(requirements), 2)
        self.assertTrue(all(c["confirmation_status"] == "needs_confirmation" for c in requirements))
        self.responses["participants"][0]["answers"][0]["confirmed_requirements"] = [
            {key: c[key] for key in ("attribute_id", "required_value", "constraint_rule", "unit")}
            for c in requirements]
        confirmed = self.process(semantic_evidence=original["semantic_evidence"])
        self.assertEqual(confirmed["preparation"]["status"], "ready")
        self.assertTrue(all(c["confirmation_status"] == "confirmed" for c in confirmed["preparation"]["constraints"]))
        self.assertEqual(self.process(semantic_evidence=confirmed["semantic_evidence"]), confirmed)

    def test_missing_new_criterion_requests_facts_without_inventing_them(self):
        self.answer({"preferences": [{"criterion": "repairable", "value": True}]})
        before = copy.deepcopy((self.planning, self.responses))
        packet = self.process()["preparation"]
        self.assertEqual(packet["status"], "needs_information")
        self.assertEqual(len(packet["fact_requests"]), 2)
        self.assertTrue(all(r["attribute_id"] == "repairable" and r["value_type"] == "boolean" for r in packet["fact_requests"]))
        self.assertTrue(all(len(c["facts"]) == 3 for c in packet["candidates"]))
        self.assertEqual((self.planning, self.responses), before)

    def test_single_question_weight_is_shared_across_distinct_criteria(self):
        self.answer({"preferences": [{"criterion": "quiet", "value": True},
                                     {"criterion": "step_free_access", "value": True}]})
        packet = self.process()["preparation"]
        self.assertEqual(packet["scoring_model"]["questions"][0]["weight"], 1)
        self.assertEqual([r["base_weight"] for r in packet["scoring_model"]["member_weights"]], [0.5, 0.5])

    def test_numeric_directions_are_not_targets(self):
        self.numeric_question()
        for text, direction in (("longer is better", "maximize"), ("lower is better", "minimize")):
            with self.subTest(text=text):
                self.answer(text)
                p = self.process()["preparation"]["preferences"][0]
                self.assertIsNone(p["preferred_value"])
                self.assertEqual(p["utility_rule"], f"numeric_{direction}_v1")
                self.assertEqual(p["direction"], direction)
                self.assertEqual(p["utility_parameters"], {"lower_bound": 10, "upper_bound": 15})

    def test_numeric_direction_with_constant_or_missing_domain(self):
        self.numeric_question()
        self.answer("longer is better")
        self.planning["options"][1]["facts"][0]["value"] = 10
        packet = self.process()["preparation"]
        self.assertEqual(packet["status"], "ready")
        self.assertEqual(packet["preferences"][0]["utility_parameters"], {"lower_bound": 10, "upper_bound": 10})
        for option in self.planning["options"]:
            option["facts"] = []
        self.planning["criteria"] = [{"attribute_id": "battery_life", "value_type": "number", "unit": "hours"}]
        packet = self.process()["preparation"]
        self.assertEqual(packet["status"], "needs_information")
        self.assertEqual(packet["preferences"][0]["utility_parameters"], {"lower_bound": None, "upper_bound": None})

    def test_numeric_range_and_strict_soft_bound(self):
        self.numeric_question()
        for value, expected in (("between 10 and 14 hours", {"lower": 10, "upper": 14, "lower_inclusive": True, "upper_inclusive": True}),
                                ("under 12 hours", {"lower": None, "upper": 12, "lower_inclusive": True, "upper_inclusive": False})):
            with self.subTest(value=value):
                self.answer(value)
                p = self.process()["preparation"]["preferences"][0]
                self.assertEqual(p["preferred_value"], expected)
                self.assertEqual(p["utility_rule"], "numeric_range_v1")

    def test_hard_numeric_range_and_direction_without_limit(self):
        self.numeric_question("hard")
        self.answer({"lower": 10, "upper": 14, "upper_inclusive": False})
        c = self.process()["preparation"]["constraints"][0]
        self.assertEqual(c["constraint_rule"], "within_range_v1")
        self.assertFalse(c["required_value"]["upper_inclusive"])
        self.answer("longer is better")
        result = self.process()
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["preparation"]["constraints"], [])

    def test_invalid_ranges_and_units_are_clarified(self):
        self.numeric_question()
        for value, code in (({"lower": 14, "upper": 10}, "CONFLICTING_ANSWER"),
                            ({"lower": 10, "upper": 10, "upper_inclusive": False}, "CONFLICTING_ANSWER"),
                            ({"lower": 10, "upper": 14, "lower_inclusive": "yes"}, "INVALID_VALUE"),
                            ("between 10 and 14 minutes", "UNIT_MISMATCH")):
            with self.subTest(value=value):
                self.answer(value)
                result = self.process()
                self.assertIn(code, [i["code"] for i in result["issues"]])
                self.assertEqual(result["preparation"]["preferences"], [])

    def test_budget_negative_values_and_mismatched_currency_are_clarified(self):
        self.planning["questions"] = [{"question_id": "preferences", "label": "Maximum budget?"}]
        for value, code in ((-50, "AMBIGUOUS_BUDGET"), ("£50", "UNIT_MISMATCH")):
            with self.subTest(value=value):
                self.answer(value)
                self.assertIn(code, [i["code"] for i in self.process()["issues"]])
        self.answer("$1,000")
        self.assertEqual(self.process()["preparation"]["constraints"][0]["required_value"], "1000")

    def test_member_weights_differ_while_question_relevance_stays_fixed(self):
        self.answer({"preferences": [{"criterion": "quiet", "value": True},
                                     {"criterion": "step_free_access", "value": True}]})
        self.planning["roster"].append("p2")
        second = copy.deepcopy(self.responses["participants"][0])
        second["participant_id"] = "p2"
        self.responses["participants"].append(second)
        baseline = self.process()["preparation"]["scoring_model"]["questions"]
        self.responses["participants"][0]["importance"] = {"quiet": 3, "step_free_access": 1}
        second["importance"] = {"quiet": 1, "step_free_access": 3}
        packet = self.process()["preparation"]
        rows = packet["scoring_model"]["member_weights"]
        self.assertEqual([r["effective_weight"] for r in rows], [0.75, 0.25, 0.25, 0.75])
        self.assertEqual(packet["scoring_model"]["questions"], baseline)
        self.assertTrue(all(i["source_question_id"] is None for i in packet["importance"]))

    def test_importance_question_is_separate_and_ordinal_policy_is_explicit(self):
        self.numeric_question()
        for option, colour in zip(self.planning["options"], ("black", "silver")):
            option["facts"].append({"criterion": "colour", "value": colour, "status": "confirmed", "source": "test"})
        self.planning["questions"].extend([{"question_id": "colour", "label": "Colour preference?", "role": "soft", "criterion": "colour", "relevance": 1},
                                          {"question_id": "importance", "label": "Which criteria matter most?", "role": "importance", "criterion": "importance"}])
        self.answer("12 hours")
        self.responses["participants"][0]["answers"].extend([
            {"question_id": "colour", "value": "black"},
            {"question_id": "importance", "value": "Battery life matters more than colour."}])
        packet = self.process()["preparation"]
        self.assertEqual(packet["status"], "ready")
        self.assertEqual([p["attribute_id"] for p in packet["preferences"]], ["battery_life", "colour"])
        self.assertIsNone(packet["scoring_model"]["questions"][-1]["weight"])
        rows = packet["scoring_model"]["member_weights"]
        self.assertEqual([r["importance_multiplier"] for r in rows], [2, 1])
        self.assertAlmostEqual(rows[0]["effective_weight"], 2 / 3)
        self.assertEqual(packet["scoring_model"]["ordinal_importance_policy"], "longest_path_tiers_v1")

    def test_cycles_zero_weights_unknown_and_hard_references_are_not_scored(self):
        self.answer({"preferences": [{"criterion": "quiet", "value": True},
                                     {"criterion": "step_free_access", "value": True}]})
        self.planning["questions"].append({"question_id": "importance", "label": "Importance?"})
        self.responses["participants"][0]["answers"].append({"question_id": "importance", "value": {}})
        for importance in ({"quiet": 0, "step_free_access": 0}, {"unknown": 2}, {"max_cost": 2},
                           "Quiet matters more than step free access. Step free access matters more than quiet."):
            with self.subTest(importance=importance):
                self.responses["participants"][0]["answers"][-1]["value"] = importance
                result = self.process()
                self.assertEqual(result["status"], "needs_clarification")
                self.assertTrue(all(r["effective_weight"] is None and r["status"] == "unresolved"
                                    for r in result["preparation"]["scoring_model"]["member_weights"]))

    def test_importance_value_cannot_contradict_an_ordinal_statement(self):
        self.answer({"preferences": [{"criterion": "quiet", "value": True},
                                     {"criterion": "step_free_access", "value": True}], "importance": {"quiet": 0}})
        self.planning["questions"].append({"question_id": "importance", "label": "Importance?"})
        self.responses["participants"][0]["answers"].append({"question_id": "importance", "value": "Quiet matters more than step free access."})
        result = self.process()
        self.assertIn("CONFLICTING_IMPORTANCE", [i["code"] for i in result["issues"]])

    def test_model_extracts_importance_paraphrase_without_inventing_ratio(self):
        class Provider:
            model = "importance-fixture"

            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "interpretations": [], "importance_relations": [
                    {"higher_criterion": "quiet", "lower_criterion": "step_free_access", "evidence": answer_text}]}

        self.answer({"preferences": [{"criterion": "quiet", "value": True},
                                     {"criterion": "step_free_access", "value": True}]})
        self.planning["questions"].append({"question_id": "importance", "label": "Importance?"})
        self.responses["participants"][0]["answers"].append({"question_id": "importance", "value": "Silence takes priority over accessible entry for me."})
        result = self.process(semantic_provider=Provider())
        self.assertEqual(result["preparation"]["status"], "ready")
        relation = result["preparation"]["importance"][0]
        self.assertEqual((relation["kind"], relation["source_type"]), ("ordering", "semantic_model"))
        self.assertNotIn("value", relation)
        self.assertEqual(self.process(semantic_evidence=result["semantic_evidence"]), result)

    def test_validation_rejects_forged_weights_and_comparison_rules(self):
        self.numeric_question()
        self.answer("longer is better")
        packet = self.process()["preparation"]
        for field in ("weight", "rule"):
            broken = copy.deepcopy(packet)
            if field == "weight":
                broken["scoring_model"]["member_weights"][0]["effective_weight"] = 0.5
            else:
                broken["preferences"][0]["utility_rule"] = "invented_v1"
            with self.assertRaises(InputError):
                validate_preparation(broken)

    def test_directional_prices_sort_decimal_bounds_numerically(self):
        self.planning["questions"] = [{"question_id": "preferences", "label": "Price preference?",
                                      "role": "soft", "criterion": "max_cost", "relevance": 1}]
        self.planning["options"][0]["facts"][1]["value"] = "9"
        self.planning["options"][1]["facts"][1]["value"] = "100"
        self.answer("cheaper is better")
        p = self.process()["preparation"]["preferences"][0]
        self.assertEqual(p["utility_parameters"], {"lower_bound": "9", "upper_bound": "100"})
        self.assertEqual(p["utility_rule"], "numeric_minimize_v1")

    def test_numeric_choice_ids_still_resolve_to_labels(self):
        self.planning["questions"] = [{"question_id": "preferences", "label": "Maximum budget?",
                                      "choices": [{"choice_id": "cap", "label": "$50"}]}]
        self.answer({"choice_id": "cap"})
        c = self.process()["preparation"]["constraints"][0]
        self.assertEqual((c["required_value"], c["constraint_rule"]), ("50", "maximum_v1"))

    def test_conflicting_confirmed_bounds_across_questions_are_rejected(self):
        self.numeric_question("hard")
        self.planning["questions"].append({"question_id": "cap", "label": "Maximum battery life?"})
        self.answer("at least 14 hours")
        self.responses["participants"][0]["answers"].append({"question_id": "cap", "value": "under 14 hours"})
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["issues"][0]["code"], "CONFLICTING_ANSWER")

    def test_invalid_member_importance_values_and_declarations_are_rejected(self):
        self.answer({"preferences": [{"criterion": "quiet", "value": True}]})
        for importance in ({"quiet": -1}, {"quiet": True}, {"quiet": float("inf")}, "quiet"):
            with self.subTest(importance=importance):
                self.responses["participants"][0]["importance"] = importance
                self.assertEqual(preprocess(self.planning, self.responses)["status"], "invalid_input")
        self.responses["participants"][0].pop("importance")
        self.planning["criteria"] = [{"attribute_id": "quiet", "value_type": "number", "unit": None}]
        self.assertEqual(preprocess(self.planning, self.responses)["status"], "invalid_input")

    def test_literal_numeric_bound_corrects_a_model_direction_label(self):
        class Provider:
            model = "mislabelled-bound"

            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "interpretations": [
                    {"criterion": "max_cost", "value": "50.00 USD", "intent": "maximize",
                     "polarity": "avoid", "must_have": True, "evidence": answer_text}]}

        self.answer("I must spend under $50")
        packet = self.process(semantic_provider=Provider())["preparation"]
        self.assertEqual(packet["preferences"], [])
        c = packet["constraints"][0]
        self.assertEqual((c["required_value"], c["constraint_rule"], c["confirmation_status"]),
                         ("50", "less_than_v1", "needs_confirmation"))
        self.answer("I must not spend under $50")
        result = self.process(semantic_provider=Provider())
        self.assertEqual(result["preparation"]["constraints"], [])
        self.assertIn("AMBIGUOUS_ANSWER", [i["code"] for i in result["issues"]])

    def test_numeric_comparative_text_is_directional_even_if_model_says_match(self):
        self.numeric_question()
        self.answer({"preferences": [{"criterion": "battery_life", "value": "greater battery life", "intent": "match"}]})
        p = self.process()["preparation"]["preferences"][0]
        self.assertEqual((p["direction"], p["utility_rule"], p["preferred_value"]),
                         ("maximize", "numeric_maximize_v1", None))

    def test_compound_answer_cannot_omit_a_required_hard_limit(self):
        self.planning["questions"] = [{"question_id": "preferences", "label": "Maximum budget?"}]
        for value in ({"preferences": []}, {"preferences": [{"criterion": "quiet", "value": True}]}):
            with self.subTest(value=value):
                self.answer(value)
                result = self.process()
                self.assertEqual(result["status"], "needs_clarification")
                self.assertIn("AMBIGUOUS_ANSWER", [i["code"] for i in result["issues"]])


if __name__ == "__main__":
    unittest.main()
