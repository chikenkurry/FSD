"""Scoped alias normalization and model equivalence with auditable replay."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from decision_service.preprocessing import preprocess
from decision_service.preprocessing.semantics import OllamaSemanticProvider, OpenAISemanticProvider
from decision_service.preprocessing.sparse import VERSION


FIXTURES = Path(__file__).parents[1] / "fixtures" / "preprocessing"


class LabelProvider:
    model = "canonical-fixture"

    def __init__(self, replies):
        self.replies = replies
        self.calls = []

    def canonicalize_sparse_label(self, payload):
        self.calls.append(copy.deepcopy(payload))
        return self.replies[payload["label"]]


def equivalent(target):
    return {"status": "equivalent", "target": target, "reason": "Same scoped meaning"}


class CanonicalizationTests(unittest.TestCase):
    def setUp(self):
        self.planning = json.loads((FIXTURES / "planning_generic.json").read_text())
        self.responses = json.loads((FIXTURES / "response_generic.json").read_text())
        self.planning["canonicalization"] = {
            "criteria": {"battery_life": ["runtime", "battery duration"], "usage_tags": ["work interests"]},
            "values": {"usage_tags": {"coding": ["programming", "software development"]}},
        }

    def process(self, **kwargs):
        result = preprocess(self.planning, self.responses, **kwargs)
        self.assertNotEqual(result["status"], "invalid_input", result.get("issues"))
        return result

    def use_usage_only(self):
        self.planning["questions"] = [{"question_id": "usage", "label": "Work interests preference?"}]
        self.responses["participants"][0]["answers"] = [{"question_id": "usage", "value": ["Programming"]}]

    def test_declared_criterion_and_tag_aliases_need_no_model(self):
        self.use_usage_only()
        packet = self.process()["preparation"]
        self.assertEqual(packet["status"], "ready")
        q = packet["scoring_model"]["questions"][0]
        self.assertEqual((q["criterion"], q["inference_source"]), ("usage_tags", "rules"))
        self.assertEqual(packet["preferences"][0]["preferred_value"], ["coding"])
        self.assertEqual(packet["preferences"][0]["evidence"], '["Programming"]')
        record = next(r for r in packet["canonicalization"]["records"] if r["original"] == "Programming")
        self.assertEqual((record["canonical"], record["source_type"]), ("coding", "declared_alias"))

    def test_single_tag_alias_can_be_parsed_locally(self):
        self.use_usage_only()
        self.responses["participants"][0]["answers"][0]["value"] = "Software development"
        self.assertEqual(self.process()["preparation"]["preferences"][0]["preferred_value"], ["coding"])

    def test_fact_aliases_preserve_source_status_original_and_input(self):
        self.use_usage_only()
        fact = self.planning["options"][0]["facts"][2]
        fact.update(criterion="work interests", value=["Programming", "Design"], status="estimated")
        before = copy.deepcopy((self.planning, self.responses))
        packet = self.process()["preparation"]
        fact = packet["candidates"][0]["facts"][2]
        self.assertEqual((fact["attribute_id"], fact["value"], fact["status"], fact["source"]),
                         ("usage_tags", ["coding", "design"], "estimated", "team assessment"))
        self.assertTrue(packet["fact_requests"])
        self.assertTrue(any(r["original"] == "work interests" for r in packet["canonicalization"]["records"]))
        self.assertEqual((self.planning, self.responses), before)

    def test_criterion_aliases_combine_automatic_question_topics(self):
        self.planning["questions"] = [
            {"question_id": "a", "label": "Runtime preference?"},
            {"question_id": "b", "label": "Battery duration preference?"},
            {"question_id": "c", "label": "Usage tags preference?"}]
        self.responses["participants"][0]["answers"] = [
            {"question_id": "a", "value": 12}, {"question_id": "b", "value": 12},
            {"question_id": "c", "value": ["programming"]}]
        weights = [q["weight"] for q in self.process()["preparation"]["scoring_model"]["questions"]]
        self.assertEqual(weights, [0.25, 0.25, 0.5])

    def test_value_aliases_are_scoped_to_the_criterion(self):
        self.use_usage_only()
        for option in self.planning["options"]:
            option["facts"].append({"criterion": "course", "value": "programming", "status": "confirmed", "source": "course guide"})
        packet = self.process()["preparation"]
        self.assertEqual(packet["candidates"][0]["facts"][-1]["value"], "programming")

    def test_aliases_cannot_merge_different_types_or_units(self):
        for kind, unit, value in (("category", None, "long"), ("number", "minutes", 720)):
            with self.subTest(kind=kind, unit=unit):
                planning = copy.deepcopy(self.planning)
                planning["options"][0]["facts"].append({"criterion": "runtime", "value": value,
                    "value_type": kind, **({"unit": unit} if unit else {}), "status": "confirmed", "source": "test"})
                result = preprocess(planning, self.responses)
                self.assertEqual(result["status"], "invalid_input")
                self.assertEqual(result["issues"][0]["code"], "CONFLICTING_FACT_TYPE")

    def test_ambiguous_aliases_chains_unknown_targets_and_numeric_tags_rejected(self):
        cases = [
            {"criteria": {"battery_life": ["same"], "usage_tags": ["same"]}},
            {"criteria": {"nonexistent": ["label"]}},
            {"criteria": {"battery_life": ["usage_tags"]}},
            {"values": {"battery_life": {"12": ["long"]}}},
            {"values": {"usage_tags": {"coding": ["work"], "design": ["work"]}}},
            {"values": {"usage_tags": {"coding": ["programming"], "programming": ["development"]}}},
            {"unexpected": True},
        ]
        for declarations in cases:
            with self.subTest(declarations=declarations):
                self.planning["canonicalization"] = declarations
                self.assertEqual(preprocess(self.planning, self.responses)["status"], "invalid_input")

    def test_duplicate_facts_after_aliasing_require_reconciliation(self):
        self.planning["options"][0]["facts"].append({"criterion": "runtime", "value": 12,
            "unit": "hours", "status": "confirmed", "source": "other quote"})
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["issues"][0]["code"], "DUPLICATE_ID")

    def test_model_tag_synonym_uses_only_existing_vocabulary_and_replays(self):
        self.use_usage_only()
        self.planning.pop("canonicalization")
        self.planning["questions"][0].update(label="Usage tags preference?")
        self.responses["participants"][0]["answers"][0]["value"] = ["Software engineering"]
        provider = LabelProvider({"software engineering": equivalent("coding")})
        result = self.process(semantic_provider=provider)
        self.assertEqual(result["preparation"]["status"], "ready")
        p = result["preparation"]["preferences"][0]
        self.assertEqual((p["preferred_value"], p["source_type"], p["status"]), (["coding"], "semantic_model", "estimated"))
        self.assertEqual(provider.calls[0]["criterion"]["attribute_id"], "usage_tags")
        self.assertIn("coding", provider.calls[0]["targets"])
        self.assertNotIn("options", provider.calls[0])
        self.assertEqual(self.process(semantic_evidence=result["semantic_evidence"]), result)

    def test_model_criterion_synonym_reuses_type_and_does_not_create_fact_request(self):
        self.planning["questions"] = [{"question_id": "runtime", "label": "Preferred power endurance?",
                                      "role": "soft", "criterion": "power_endurance", "relevance": 1}]
        self.responses["participants"][0]["answers"] = [{"question_id": "runtime", "value": 12}]
        provider = LabelProvider({"power_endurance": equivalent("battery_life")})
        result = self.process(semantic_provider=provider)
        self.assertEqual(result["preparation"]["preferences"][0]["attribute_id"], "battery_life")
        self.assertEqual(result["preparation"]["fact_requests"], [])
        self.assertEqual(self.process(semantic_evidence=result["semantic_evidence"]), result)

    def test_unresolved_model_labels_are_not_scored(self):
        self.use_usage_only()
        self.responses["participants"][0]["answers"][0]["value"] = ["Development"]
        provider = LabelProvider({"development": {"status": "unresolved", "target": None, "reason": "Could mean coding or design"}})
        result = self.process(semantic_provider=provider)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("AMBIGUOUS_CANONICAL_LABEL", [i["code"] for i in result["issues"]])
        self.assertEqual(result["preparation"]["preferences"], [])
        self.assertEqual(self.process(semantic_evidence=result["semantic_evidence"]), result)

    def test_distinct_tags_remain_distinct_without_changing_fact_evidence(self):
        self.use_usage_only()
        self.responses["participants"][0]["answers"][0]["value"] = ["Gardening"]
        provider = LabelProvider({"gardening": {"status": "distinct", "target": None, "reason": "A different interest"}})
        result = self.process(semantic_provider=provider)
        self.assertEqual(result["preparation"]["preferences"][0]["preferred_value"], ["gardening"])
        self.assertEqual(result["preparation"]["preferences"][0]["source_type"], "member_response")
        self.assertFalse(any("gardening" in f["value"] for c in result["preparation"]["candidates"] for f in c["facts"] if f["value_type"] == "tag_set"))

    def test_model_cannot_invent_a_target_or_return_a_target_for_ambiguity(self):
        self.use_usage_only()
        self.responses["participants"][0]["answers"][0]["value"] = ["Development"]
        for reply in (equivalent("new-tag"), {"status": "unresolved", "target": "coding", "reason": "Unsure"}):
            result = preprocess(self.planning, self.responses, semantic_provider=LabelProvider({"development": reply}))
            self.assertEqual(result["status"], "invalid_input")
            self.assertEqual(result["issues"][0]["code"], "INVALID_SEMANTIC_RESULT")

    def test_equivalent_assessment_is_cached_for_repeated_labels(self):
        self.use_usage_only()
        self.responses["participants"][0]["answers"][0]["value"] = ["Building software", "Building software"]
        provider = LabelProvider({"building software": equivalent("coding")})
        result = self.process(semantic_provider=provider)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(result["preparation"]["preferences"][0]["preferred_value"], ["coding"])
        self.assertEqual(result["preparation"]["scoring_model"]["member_weights"][0]["effective_weight"], 1)

    def test_model_mapped_hard_tag_still_needs_typed_confirmation(self):
        self.use_usage_only()
        self.planning["questions"][0].update(label="Required usage tags?", role="hard", criterion="usage_tags", relevance=0)
        self.responses["participants"][0]["answers"][0]["value"] = ["Building software"]
        provider = LabelProvider({"building software": equivalent("coding")})
        result = self.process(semantic_provider=provider)
        self.assertEqual(result["preparation"]["constraints"][0]["confirmation_status"], "needs_confirmation")
        self.responses["participants"][0]["answers"][0]["confirmed_requirement"] = {
            "attribute_id": "work interests", "required_value": ["programming"], "constraint_rule": "contains_all_v1", "unit": None}
        result = self.process(semantic_evidence=result["semantic_evidence"])
        self.assertEqual(result["preparation"]["constraints"][0]["confirmation_status"], "confirmed")

    def test_model_mapped_hard_question_requires_confirmation(self):
        self.planning["questions"] = [{"question_id": "runtime", "label": "Minimum power endurance?", "role": "hard",
                                      "criterion": "power_endurance", "relevance": 0}]
        self.responses["participants"][0]["answers"] = [{"question_id": "runtime", "value": 12}]
        result = self.process(semantic_provider=LabelProvider({"power_endurance": equivalent("battery_life")}))
        self.assertEqual(result["preparation"]["constraints"][0]["confirmation_status"], "needs_confirmation")

    def test_numeric_punctuation_and_programming_language_symbols_are_distinct(self):
        self.use_usage_only()
        self.responses["participants"][0]["answers"][0]["value"] = ["C++", "C#", "C"]
        packet = self.process()["preparation"]
        self.assertEqual(packet["preferences"][0]["preferred_value"], ["c", "c#", "c++"])
        self.planning["questions"][0].update(role="soft", criterion="usage_tags", relevance=1)
        self.responses["participants"][0]["answers"][0]["value"] = {"preferences": [
            {"criterion": "Battery-Life", "value": 12}]}
        self.assertEqual(self.process()["preparation"]["preferences"][0]["attribute_id"], "battery_life")

    def test_importance_aliases_use_same_criteria_for_weights(self):
        self.responses["participants"][0]["importance"] = {"runtime": 3, "work interests": 1}
        packet = self.process()["preparation"]
        self.assertEqual([r["effective_weight"] for r in packet["scoring_model"]["member_weights"]], [0.75, 0.25])
        self.responses["participants"][0].pop("importance")
        self.planning["questions"].append({"question_id": "importance", "label": "Importance?"})
        self.responses["participants"][0]["answers"].append({"question_id": "importance", "value": "Runtime matters more than work interests."})
        self.assertEqual([r["importance_multiplier"] for r in self.process()["preparation"]["scoring_model"]["member_weights"]], [2, 1])

    def test_missing_canonical_evidence_and_old_processing_are_rejected(self):
        self.use_usage_only()
        self.responses["participants"][0]["answers"][0]["value"] = ["Building software"]
        evidence = self.process(semantic_provider=LabelProvider({"building software": equivalent("coding")}))["semantic_evidence"]
        missing = copy.deepcopy(evidence)
        missing["canonical_assessments"] = {}
        result = preprocess(self.planning, self.responses, semantic_evidence=missing)
        self.assertEqual(result["issues"][0]["code"], "MISSING_CANONICAL_EVIDENCE")
        evidence["processing_version"] = "sparse-v5"
        self.assertEqual(preprocess(self.planning, self.responses, semantic_evidence=evidence)["issues"][0]["code"], "STALE_SEMANTIC_EVIDENCE")

    def test_rules_only_canonicalization_can_replay_empty_assessments(self):
        self.use_usage_only()
        evidence = {"option_snapshot_id": self.planning["option_snapshot_id"], "response_snapshot_id": self.responses["response_snapshot_id"],
                    "processing_version": VERSION, "question_assessments": {}, "answer_assessments": {}, "canonical_assessments": {},
                    "canonicalization_declarations": self.planning["canonicalization"]}
        self.assertEqual(self.process(semantic_evidence=evidence)["preparation"]["status"], "ready")

    def test_unknown_fact_stays_unknown_and_model_does_not_canonicalize_fact_values(self):
        self.use_usage_only()
        self.responses["participants"][0]["answers"][0]["value"] = ["coding"]
        fact = self.planning["options"][0]["facts"][2]
        fact.update(value=None, value_type="tag_set", status="unknown")
        provider = LabelProvider({})
        packet = self.process(semantic_provider=provider)["preparation"]
        self.assertEqual(provider.calls, [])
        self.assertIsNone(packet["candidates"][0]["facts"][2]["value"])
        self.assertEqual(packet["candidates"][0]["facts"][2]["status"], "unknown")

    def test_transport_providers_use_equivalence_schema(self):
        payload = {"kind": "value", "label": "programming", "targets": ["coding"], "criterion": {"attribute_id": "usage_tags"}}
        for provider in (OllamaSemanticProvider(), OpenAISemanticProvider(api_key="test")):
            with self.subTest(provider=type(provider).__name__), patch.object(provider, "_request", return_value=equivalent("coding")) as request:
                self.assertEqual(provider.canonicalize_sparse_label(payload), equivalent("coding"))
                self.assertIn(payload, request.call_args.args)

    def test_ambiguous_question_and_structured_meaning_request_clarification(self):
        provider = LabelProvider({"performance": {"status": "unresolved", "target": None, "reason": "Could refer to runtime or usage capability"}})
        self.planning["questions"] = [{"question_id": "runtime", "label": "Performance preference?", "role": "soft",
                                      "criterion": "performance", "relevance": 1}]
        self.responses["participants"][0]["answers"] = [{"question_id": "runtime", "value": 12}]
        result = self.process(semantic_provider=provider)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["preparation"]["preferences"], [])
        self.assertEqual(result["preparation"]["scoring_model"]["questions"][0]["role"], "unclassified")
        self.use_usage_only()
        self.responses["participants"][0]["answers"][0]["value"] = {"preferences": [{"criterion": "performance", "value": 12}]}
        result = self.process(semantic_provider=provider)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["preparation"]["preferences"], [])

    def test_changed_aliases_do_not_reuse_frozen_assessments(self):
        self.use_usage_only()
        self.responses["participants"][0]["answers"][0]["value"] = ["Building software"]
        evidence = self.process(semantic_provider=LabelProvider({"building software": equivalent("coding")}))["semantic_evidence"]
        self.planning["canonicalization"]["values"]["usage_tags"]["coding"].append("Building software")
        result = preprocess(self.planning, self.responses, semantic_evidence=evidence)
        self.assertEqual(result["issues"][0]["code"], "STALE_SEMANTIC_EVIDENCE")

    def test_known_labels_do_not_call_the_canonicalization_provider(self):
        provider = LabelProvider({})
        result = self.process(semantic_provider=provider)
        self.assertEqual(result["preparation"]["status"], "ready")
        self.assertEqual(provider.calls, [])

    def test_open_text_aliases_preserve_polarity_and_clause_evidence(self):
        class Provider:
            model = "open-alias-fixture"

            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "interpretations": [
                    {"criterion": "work interests", "value": "programming", "evidence": "I avoid programming",
                     "polarity": "avoid", "intent": "match", "must_have": False}]}

        self.use_usage_only()
        self.responses["participants"][0]["answers"][0]["value"] = "I avoid programming."
        result = self.process(semantic_provider=Provider())
        preference = result["preparation"]["preferences"][0]
        self.assertEqual((preference["attribute_id"], preference["preferred_value"], preference["polarity"], preference["evidence"]),
                         ("usage_tags", ["coding"], "avoid", "I avoid programming"))
        self.assertEqual(self.process(semantic_evidence=result["semantic_evidence"]), result)

    def test_declared_form_choices_bypass_model_equivalence(self):
        self.planning["questions"] = [{"question_id": "colour", "label": "Colour preference?", "choices": ["Red", "Blue"]}]
        self.planning["options"] = [{"option_id": "blue", "title": "Blue device", "facts": [
            {"criterion": "colour", "value": "blue", "status": "confirmed", "source": "test"}]}]
        self.planning.pop("canonicalization")
        self.responses["participants"][0]["answers"] = [{"question_id": "colour", "value": "Red"}]
        provider = LabelProvider({"red": equivalent("blue")})
        packet = self.process(semantic_provider=provider)["preparation"]
        self.assertEqual(packet["preferences"][0]["preferred_value"], "red")
        self.assertEqual(provider.calls, [])


if __name__ == "__main__":
    unittest.main()
