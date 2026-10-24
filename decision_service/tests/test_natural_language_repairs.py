"""Comparative grammar and evidence repairs across arbitrary typed criteria."""

import copy
import json
import unittest
from pathlib import Path

from decision_service.preprocessing import preprocess
from decision_service.preprocessing.comparatives import comparative_direction
from decision_service.tests.test_preference_semantics import snapshots


class ComparativeInterpretationTests(unittest.TestCase):
    def process(self, text, reply, *, hard=False):
        planning, responses = snapshots([("metric", "number", "units")], [{"metric": 10}, {"metric": 30}],
            {"question_id": "preference", "label": "Metric preference?", "role": "hard" if hard else "soft",
             "criterion": "metric", "relevance": 0 if hard else 1})
        responses["participants"][0]["answers"][0]["value"] = text
        class Provider:
            model = "misclassified-comparative"
            def extract_sparse_answer(self, *args):
                return copy.deepcopy(reply)
        return preprocess(planning, responses, semantic_provider=Provider())

    def interpretation(self, evidence, value="an unparseable model value", intent="match", must=True, polarity="prefer"):
        return {"status": "resolved", "interpretations": [{"criterion": "metric", "value": value,
                "evidence": evidence, "intent": intent, "must_have": must, "polarity": polarity}]}

    def test_comparative_templates_generalize_without_option_or_criterion_dictionaries(self):
        for text, expected in (
            ("The less vibration it produces, the better.", "minimize"),
            ("The longer the signal lasts, the better.", "maximize"),
            ("I would favor whichever can handle the larger quantity.", "maximize"),
            ("I prefer a lighter load.", "minimize"),
            ("I would rather pick a lighter unit.", "minimize"),
            ("Lower intensity would be better.", "minimize"),
        ):
            with self.subTest(text=text):
                result = self.process(text, self.interpretation(text))
                packet = result["preparation"]
                self.assertEqual(packet["status"], "ready", result["issues"])
                self.assertEqual(packet["constraints"], [])
                p = packet["preferences"][0]
                self.assertEqual((p["numeric_intent"], p["preferred_value"], p["utility_rule"]),
                                 (expected, None, f"numeric_{expected}_v1"))
                self.assertEqual((p["source_type"], p["status"]), ("semantic_model", "estimated"))

    def test_rejected_historical_model_replies_are_repaired(self):
        root = Path(__file__).parents[1] / "fixtures" / "evaluation"
        dataset = json.loads((root / "processing_challenge.json").read_text())
        report = json.loads((root / "recorded" / "processing_challenge_v1" / "live.json").read_text())
        failed = [r for r in report["results"] if not r["passed"]]
        self.assertEqual(len(failed), 2)
        for recorded in failed:
            with self.subTest(case=recorded["case_id"]):
                case = next(c for c in dataset["cases"] if c["case_id"] == recorded["case_id"])
                raw = recorded["model_calls"][0]["response"]
                class Provider:
                    model = "historical-reply"
                    def extract_sparse_answer(self, *args):
                        return copy.deepcopy(raw)
                result = preprocess(case["planning"], case["responses"], semantic_provider=Provider())
                self.assertEqual(result["preparation"]["status"], "ready", result["issues"])
                self.assertEqual(result["preparation"]["constraints"], [])

    def test_explicit_hard_question_is_not_softened_by_comparative_wording(self):
        text = "The less vibration it produces, the better."
        result = self.process(text, self.interpretation(text), hard=True)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["preparation"]["constraints"], [])

    def test_explicit_requirement_wording_still_needs_a_numeric_limit(self):
        text = "I must choose a larger quantity."
        result = self.process(text, self.interpretation(text, intent="maximize", value=""))
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["preparation"]["constraints"], [])

    def test_only_if_requirement_is_not_softened_by_preference_words(self):
        text = "I would favor this only if it has a higher quantity."
        result = self.process(text, self.interpretation(text, intent="maximize", value=""))
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["preparation"]["constraints"], [])

    def test_bounded_requirement_is_not_rewritten_as_direction(self):
        text = "I prefer higher intensity but I must stay under 20 units."
        reply = self.interpretation("I must stay under 20 units", value="20 units", intent="less_than")
        result = self.process(text, reply)
        c = result["preparation"]["constraints"][0]
        self.assertEqual((c["constraint_rule"], c["required_value"], c["confirmation_status"]),
                         ("less_than_v1", 20, "needs_confirmation"))

    def test_unrelated_requirement_clause_does_not_harden_a_comparative(self):
        text = "The more intensity it provides, the better. I must have an indoor option."
        result = self.process(text, self.interpretation("The more intensity it provides, the better"))
        self.assertEqual(result["preparation"]["constraints"], [])
        self.assertEqual(result["preparation"]["preferences"][0]["numeric_intent"], "maximize")

    def test_negated_bounded_compound_and_ambiguous_comparatives_are_not_repaired(self):
        for text in ("I do not prefer a higher value", "I prefer less than 20 units", "I prefer higher A and lower B",
                     "I prefer a larger value than before", "I prefer tea and less sugar", "More or less is fine"):
            with self.subTest(text=text):
                self.assertIsNone(comparative_direction(text))

    def test_category_preference_does_not_become_a_numeric_direction(self):
        planning, responses = snapshots([("style", "category", None)], [{"style": "classic"}, {"style": "modern"}],
                                        {"question_id": "style", "label": "Style preference?", "role": "soft", "criterion": "style", "relevance": 1})
        text = "I favour the more modern style."
        responses["participants"][0]["answers"][0]["value"] = text
        class Provider:
            model = "category-test"
            def extract_sparse_answer(self, *args):
                return {"status": "resolved", "interpretations": [{"criterion": "style", "value": "modern",
                    "evidence": text, "intent": "match", "must_have": True, "polarity": "prefer"}]}
        p = preprocess(planning, responses, semantic_provider=Provider())["preparation"]["preferences"][0]
        self.assertEqual((p["utility_rule"], p["preferred_value"]), ("attribute_match_v1", "modern"))

    def test_label_only_soft_answer_cannot_be_promoted_to_a_requirement(self):
        planning, responses = snapshots([("category", "category", None)], [{"category": "alpha"}, {"category": "beta"}],
                                        {"question_id": "choice", "label": "Category preference?", "role": "soft", "criterion": "category", "relevance": 1})
        responses["participants"][0]["answers"][0]["value"] = "Gamma"
        class Provider:
            model = "label-hard-error"
            def extract_sparse_answer(self, *args):
                return {"status": "resolved", "interpretations": [{"criterion": "category", "value": "gamma",
                    "evidence": "Gamma", "intent": "match", "must_have": True, "polarity": "prefer"}]}
        packet = preprocess(planning, responses, semantic_provider=Provider())["preparation"]
        self.assertEqual(packet["constraints"], [])
        self.assertEqual(packet["preferences"][0]["preferred_value"], "gamma")

    def test_label_only_evidence_cannot_hide_a_requirement_elsewhere_in_the_answer(self):
        from decision_service.preprocessing.generic_evidence import scoped_interpretation
        item = {"criterion": "category", "value": "gamma", "evidence": "gamma", "must_have": True}
        result = scoped_interpretation(item, "I must have gamma", "soft", "test", question_criterion="category")
        self.assertTrue(result["must_have"])

    def test_single_category_token_uses_scoped_equivalence_without_extraction(self):
        planning, responses = snapshots([("dimension", "category", None)], [{"dimension": "alpha"}, {"dimension": "beta"}],
                                        {"question_id": "choice", "label": "Dimension preference?", "role": "soft", "criterion": "dimension", "relevance": 1})
        responses["participants"][0]["answers"][0]["value"] = "Alternate"
        class Provider:
            model = "scoped-label-only"
            def canonicalize_sparse_label(self, payload):
                return {"status": "equivalent", "target": "alpha", "reason": "Contextual synonym supplied by the model"}
            def extract_sparse_answer(self, *args):
                raise AssertionError("A typed category token must not ask a model to infer obligation")
        packet = preprocess(planning, responses, semantic_provider=Provider())["preparation"]
        self.assertEqual(packet["constraints"], [])
        self.assertEqual(packet["preferences"][0]["preferred_value"], "alpha")
        self.assertEqual(packet["preferences"][0]["source_type"], "semantic_model")

    def test_multiword_category_requirement_still_uses_semantic_extraction(self):
        planning, responses = snapshots([("dimension", "category", None)], [{"dimension": "alpha"}, {"dimension": "beta"}],
                                        {"question_id": "choice", "label": "Dimension preference?", "role": "soft", "criterion": "dimension", "relevance": 1})
        responses["participants"][0]["answers"][0]["value"] = "I must have alpha"
        class Provider:
            model = "clause-extractor"
            def extract_sparse_answer(self, *args):
                return {"status": "resolved", "interpretations": [{"criterion": "dimension", "value": "alpha",
                    "evidence": "I must have alpha", "must_have": True, "intent": "match", "polarity": "prefer"}]}
        c = preprocess(planning, responses, semantic_provider=Provider())["preparation"]["constraints"][0]
        self.assertEqual(c["confirmation_status"], "needs_confirmation")


if __name__ == "__main__":
    unittest.main()
