"""Sparse grad-trip handoff: grounded meaning and visible missing evidence."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from decision_service.preprocessing import preprocess


FIXTURES = Path(__file__).parents[1] / "fixtures" / "preprocessing"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class FakeProvider:
    model = "fake-trip-v1"

    def classify_question(self, question, context):
        label = question["label"].casefold()
        if "availability" in label:
            return {"role": "hard", "criterion": "availability", "relevance": 0, "reason": "Dates constrain the choice"}
        if "budget" in label:
            return {"role": "hard", "criterion": "max_cost", "relevance": 0, "reason": "Cost limits constrain the choice"}
        if "how many days" in label:
            return {"role": "soft", "criterion": "duration_days", "relevance": 0.8, "reason": "Duration matters"}
        if "personal preference" in label:
            return {"role": "soft", "criterion": "personal_interests", "relevance": 1, "reason": "Interests matter"}
        if "food" in label:
            return {"role": "soft", "criterion": "food", "relevance": 0.5, "reason": "Food matters"}
        if "subject" in label:
            return {"role": "informational", "criterion": "academic_interests", "relevance": 0, "reason": "No link to the decision"}
        return {"role": "soft", "criterion": "comfort", "relevance": 0.6, "reason": "Comfort matters"}

    def extract_sparse_answer(self, question, answer_text, context):
        if answer_text == "I like hiking and museums":
            evidence = ["hiking", "museums"]
        else:
            evidence = [answer_text]
        return {"status": "resolved", "interpretations": [
            {"criterion": question["criterion"], "value": value.casefold(), "evidence": value, "must_have": False}
            for value in evidence
        ]}

    def suggest_option_tags(self, option, criteria, context):
        return {"suggestions": [{"criterion": criteria[0], "value": "regional cuisine", "reason": "Worth investigating"}]}


class SparsePreprocessingTests(unittest.TestCase):
    def setUp(self):
        self.planning = fixture("planning_grad_trip.json")
        self.responses = fixture("response_grad_trip.json")

    def test_sparse_trip_preserves_unknown_facts_and_zero_subject_weight(self):
        result = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.assertEqual(result["status"], "provisional")
        value = result["preparation"]
        self.assertEqual(value["context"]["schema_version"], "sparse-v3")
        self.assertEqual([c["title"] for c in value["candidates"]], self.planning["options"])
        self.assertEqual(value["candidates"][0]["facts"], [])
        self.assertEqual(value["candidates"][0]["tag_suggestions"][0]["status"], "hypothesis")
        self.assertIn("food", value["candidates"][0]["missing_criteria"])
        self.assertIn("personal_interests", value["candidates"][0]["missing_criteria"])
        self.assertNotIn("availability", value["candidates"][0]["missing_criteria"])
        self.assertEqual(len(value["scenario_requests"]), 12)
        seven_day = next(s for s in value["scenario_requests"] if s["option_id"] == "japan" and s["duration_days"] == 7)
        self.assertEqual((seven_day["earliest_start_date"], seven_day["latest_start_date"]), ("2027-06-03", "2027-06-04"))
        self.assertIn("MISSING_OPTION_FACTS", [i["code"] for i in result["issues"]])
        questions = {q["question_id"]: q for q in value["scoring_model"]["questions"]}
        self.assertEqual((questions["q1"]["role"], questions["q1"]["weight"]), ("hard", None))
        self.assertEqual((questions["q3"]["role"], questions["q3"]["weight"]), ("hard", None))
        self.assertEqual((questions["q6"]["role"], questions["q6"]["weight"]), ("informational", None))
        self.assertAlmostEqual(sum(q["weight"] for q in questions.values() if q["weight"] is not None), 1.0)
        duration = next(p for p in value["preferences"] if p["source_question_id"] == "q2" and p["participant_id"] == "p1")
        self.assertEqual((duration["kind"], duration["status"]), ("indifferent", "explicitly_indifferent"))
        interests = next(p for p in value["preferences"] if p["source_question_id"] == "q4" and p["participant_id"] == "p1")
        self.assertEqual(interests["preferred_value"], ["hiking", "museums"])
        budget = next(c for c in value["constraints"] if c["source_question_id"] == "q3" and c["participant_id"] == "p1")
        self.assertEqual((budget["required_value"], budget["unit"], budget["constraint_rule"]), ("3000", "SGD", "maximum_v1"))
        dates = next(c for c in value["constraints"] if c["source_question_id"] == "q1" and c["participant_id"] == "p1")
        self.assertEqual(dates["required_value"], [{"start_date": "2027-06-01", "end_date": "2027-06-12"}])

    def test_without_model_keeps_open_meaning_unresolved(self):
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "provisional")
        self.assertIn("UNKNOWN_QUESTION_ROLE", [i["code"] for i in result["issues"]])
        self.assertEqual(next(q for q in result["preparation"]["scoring_model"]["questions"] if q["question_id"] == "q5")["role"], "unclassified")
        self.assertTrue(any(a["question_id"] == "q5" for a in result["preparation"]["unclassified_answers"]))
        self.assertFalse(any(p["source_question_id"] == "q4" for p in result["preparation"]["preferences"]))

    def test_informational_subject_can_be_skipped(self):
        self.responses["participants"][0]["answers"].pop()
        result = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.assertEqual(result["status"], "provisional")
        self.assertNotIn("MISSING_ANSWER", [i["code"] for i in result["issues"]])

    def test_model_evidence_can_be_replayed(self):
        original = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.assertIn("switzerland", original["semantic_evidence"]["option_suggestions"])
        replay = preprocess(self.planning, self.responses, semantic_evidence=original["semantic_evidence"])
        self.assertEqual(replay, original)
        stale = copy.deepcopy(original["semantic_evidence"])
        stale["response_snapshot_id"] = "other"
        self.assertEqual(preprocess(self.planning, self.responses, semantic_evidence=stale)["status"], "invalid_input")

    def test_option_suggestion_cannot_claim_a_hard_constraint(self):
        class BadProvider(FakeProvider):
            def suggest_option_tags(self, option, criteria, context):
                return {"suggestions": [{"criterion": "max_cost", "value": "cheap", "reason": "Guess"}]}

        result = preprocess(self.planning, self.responses, semantic_provider=BadProvider())
        self.assertEqual(result["status"], "invalid_input")

    def test_unrecognized_question_uses_model_classification(self):
        self.planning["questions"].append({"question_id": "q7", "label": "How important is comfort?"})
        for member in self.responses["participants"]:
            member["answers"].append({"question_id": "q7", "value": "Comfortable hotels"})
        result = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        question = next(q for q in result["preparation"]["scoring_model"]["questions"] if q["question_id"] == "q7")
        self.assertEqual((question["role"], question["criterion"], question["inference_source"]), ("soft", "comfort", "model"))
        self.assertIn("q7", result["semantic_evidence"]["question_assessments"])

    def test_vague_availability_needs_member_clarification(self):
        self.responses["participants"][0]["answers"][0]["value"] = "Sometime in December"
        result = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("AMBIGUOUS_AVAILABILITY", [i["code"] for i in result["issues"]])

    def test_separate_dates_are_not_assumed_to_be_a_continuous_window(self):
        self.responses["participants"][0]["answers"][0]["value"] = "2027-06-01 or 2027-06-12"
        result = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.assertIn("AMBIGUOUS_AVAILABILITY", [i["code"] for i in result["issues"]])

    def test_model_extracts_grounded_natural_language_dates_and_replays(self):
        class DateProvider(FakeProvider):
            def extract_sparse_dates(self, question, answer_text, context):
                return {"status": "resolved", "intervals": [
                    {"start_date": "2027-06-01", "end_date": "2027-06-12", "evidence": answer_text}
                ]}

        self.responses["participants"][0]["answers"][0]["value"] = "1 to 12 June 2027"
        original = preprocess(self.planning, self.responses, semantic_provider=DateProvider())
        self.assertEqual(original["status"], "needs_clarification")
        self.assertIn("CONFIRM_REQUIREMENT", [i["code"] for i in original["issues"]])
        self.assertIn("p1", original["semantic_evidence"]["date_assessments"])
        self.assertEqual(preprocess(self.planning, self.responses, semantic_evidence=original["semantic_evidence"]), original)

    def test_model_cannot_add_an_unstated_year(self):
        class DateProvider(FakeProvider):
            def extract_sparse_dates(self, question, answer_text, context):
                return {"status": "resolved", "intervals": [
                    {"start_date": "2027-06-01", "end_date": "2027-06-12", "evidence": answer_text}
                ]}

        self.responses["participants"][0]["answers"][0]["value"] = "1 to 12 June"
        result = preprocess(self.planning, self.responses, semantic_provider=DateProvider())
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("AMBIGUOUS_AVAILABILITY", [i["code"] for i in result["issues"]])
        self.assertFalse(any(c["attribute_id"] == "availability" and c["participant_id"] == "p1"
                             for c in result["preparation"]["constraints"]))

    def test_nonoverlapping_dates_do_not_produce_schedule_scenarios(self):
        self.responses["participants"][1]["answers"][0]["value"] = "2027-07-01 to 2027-07-10"
        result = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.assertEqual(result["preparation"]["scenario_requests"], [])
        self.assertIn("NO_SCHEDULE_SCENARIO", [i["code"] for i in result["issues"]])

    def test_provided_fact_keeps_source_and_other_gaps(self):
        self.planning["options"][0] = {"option_id": "switzerland", "title": "Switzerland", "facts": [
            {"criterion": "food", "value": "Vegetarian options documented", "status": "confirmed", "source": "leader"}
        ]}
        result = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        candidate = result["preparation"]["candidates"][0]
        self.assertEqual(candidate["facts"][0]["source"], "leader")
        self.assertNotIn("food", candidate["missing_criteria"])
        self.assertIn("personal_interests", candidate["missing_criteria"])

    def test_estimated_option_fact_stays_provisional(self):
        self.planning["options"][0] = {"title": "Switzerland", "facts": [
            {"criterion": "food", "value": ["cheese"], "status": "estimated", "source": "model hypothesis"}
        ]}
        result = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.assertIn("ESTIMATED_OPTION_FACTS", [i["code"] for i in result["issues"]])

    def test_without_duration_option_facts_are_requested(self):
        self.planning["questions"] = [q for q in self.planning["questions"] if q["question_id"] != "q2"]
        for member in self.responses["participants"]:
            member["answers"] = [a for a in member["answers"] if a["question_id"] != "q2"]
        result = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.assertEqual(result["preparation"]["scenario_requests"], [])
        self.assertIn("MISSING_OPTION_FACTS", [i["code"] for i in result["issues"]])

    def test_sourced_facts_still_require_an_execution_adapter(self):
        baseline = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.planning["options"] = [
            {"option_id": c["option_id"], "title": c["title"], "facts": [
                {"criterion": "food", "value": ["local cuisine"], "status": "confirmed", "source": "leader"},
                {"criterion": "personal_interests", "value": ["nature", "museums"], "status": "confirmed", "source": "leader"},
            ]} for c in baseline["preparation"]["candidates"]
        ]
        self.planning["scenario_costs"] = [
            {"option_id": s["option_id"], "duration_days": s["duration_days"],
             "earliest_start_date": s["earliest_start_date"],
             "latest_start_date": s["latest_start_date"],
             "amount": "2500", "currency": "SGD", "scope": "per_person_total_including_transport",
             "status": "confirmed", "source": "reviewed quote"}
            for s in baseline["preparation"]["scenario_requests"]
        ]
        result = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.assertEqual(result["status"], "provisional")
        self.assertEqual([i["code"] for i in result["issues"]], ["EXECUTION_ADAPTER_REQUIRED"])
        self.assertIsNone(result["algorithm_input"])
        self.assertEqual(result["preparation"]["scenario_requests"][0]["cost_evidence"]["amount"], "2500")

        self.planning["scenario_costs"][0]["status"] = "estimated"
        estimated = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.assertEqual(estimated["status"], "provisional")
        self.assertIn("ESTIMATED_SCENARIO_COST", [i["code"] for i in estimated["issues"]])

        self.planning["scenario_costs"][0]["status"] = "confirmed"
        self.planning["scenario_costs"][0]["scope"] = "accommodation_only"
        wrong_scope = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.assertEqual(wrong_scope["status"], "invalid_input")
        self.assertIn("INVALID_COST_SCOPE", [i["code"] for i in wrong_scope["issues"]])

    def test_model_must_have_is_not_silently_enforced(self):
        class MustHaveProvider(FakeProvider):
            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "interpretations": [{"criterion": question["criterion"], "value": "required", "evidence": answer_text, "must_have": True}]}

        result = preprocess(self.planning, self.responses, semantic_provider=MustHaveProvider())
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("AMBIGUOUS_ANSWER", [i["code"] for i in result["issues"]])
        inferred = [c for c in result["preparation"]["constraints"] if c["source_type"] == "semantic_model"]
        self.assertEqual(inferred, [])

    def test_unrelated_purchase_decision_uses_option_facts_without_dates(self):
        planning = {
            "round_id": "laptop-1", "option_revision": "1", "option_snapshot_id": "laptops-1",
            "decision_question": "Which laptop should the team buy?", "currency": "USD",
            "cost_scope": "per_device_total", "roster": ["p1"],
            "options": [
                {"title": "Model A", "facts": [
                    {"criterion": "max_cost", "value": "1200", "unit": "USD", "context": {"scope": "per_device_total"}, "status": "confirmed", "source": "vendor quote"},
                    {"criterion": "battery_life", "value": 12, "unit": "hours", "status": "confirmed", "source": "vendor specification"},
                ]},
                {"title": "Model B", "facts": [
                    {"criterion": "max_cost", "value": "1400", "unit": "USD", "context": {"scope": "per_device_total"}, "status": "confirmed", "source": "vendor quote"},
                    {"criterion": "battery_life", "value": 15, "unit": "hours", "status": "confirmed", "source": "vendor specification"},
                ]},
            ],
            "questions": [
                {"question_id": "budget", "label": "Maximum budget?", "role": "hard", "criterion": "max_cost"},
                {"question_id": "battery", "label": "Battery life preference?", "role": "soft", "criterion": "battery_life", "relevance": 0.8},
            ],
        }
        responses = {"round_id": "laptop-1", "option_revision": "1", "response_snapshot_id": "answers-1",
                     "participants": [{"participant_id": "p1", "response_status": "complete", "answers": [
                         {"question_id": "budget", "value": "$1500"},
                         {"question_id": "battery", "value": "No preference"},
                     ]}]}
        result = preprocess(planning, responses)
        self.assertEqual(result["status"], "provisional")
        self.assertEqual([i["code"] for i in result["issues"]], ["EXECUTION_ADAPTER_REQUIRED"])
        self.assertIsNone(result["algorithm_input"])
        self.assertEqual(result["preparation"]["scenario_requests"], [])
        self.assertEqual(result["preparation"]["scoring_model"]["questions"][1]["weight"], 1.0)

    def test_subject_relevance_changes_with_the_decision(self):
        class MuseumProvider(FakeProvider):
            def classify_question(self, question, context):
                return {"role": "soft", "criterion": "academic_interests", "relevance": 0.9,
                        "reason": "The options are subject-themed exhibits"}

            def suggest_option_tags(self, option, criteria, context):
                return {"suggestions": []}

        planning = {"round_id": "museum-1", "option_revision": "1", "option_snapshot_id": "exhibits-1",
                    "decision_question": "Which museum exhibit should we visit?", "roster": ["p1"],
                    "options": [
                        {"title": "Science exhibit", "facts": [{"criterion": "academic_interests", "value": ["physics"], "status": "confirmed", "source": "museum"}]},
                        {"title": "Art exhibit", "facts": [{"criterion": "academic_interests", "value": ["art"], "status": "confirmed", "source": "museum"}]},
                    ],
                    "questions": [{"question_id": "subject", "label": "Favourite Subject"}]}
        responses = {"round_id": "museum-1", "option_revision": "1", "response_snapshot_id": "answers-1",
                     "participants": [{"participant_id": "p1", "response_status": "complete", "answers": [
                         {"question_id": "subject", "value": "Physics"},
                     ]}]}
        result = preprocess(planning, responses, semantic_provider=MuseumProvider())
        self.assertEqual(result["status"], "provisional")
        self.assertEqual([i["code"] for i in result["issues"]], ["EXECUTION_ADAPTER_REQUIRED"])
        self.assertIsNone(result["algorithm_input"])
        question = result["preparation"]["scoring_model"]["questions"][0]
        self.assertEqual((question["role"], question["weight"]), ("soft", 1.0))


if __name__ == "__main__":
    unittest.main()
