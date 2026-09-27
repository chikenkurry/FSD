"""Contract and semantic boundary tests using frozen, representative inputs."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from decision_service.preprocessing import preprocess
from decision_service.preprocessing.candidates import generate_candidates


FIXTURES = Path(__file__).parents[1] / "fixtures" / "preprocessing"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class PreprocessingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planning = fixture("planning_snapshot.json")
        self.responses = fixture("response_snapshot.json")

    def test_handoff_from_structured_and_open_answers(self) -> None:
        expected = fixture("expected_checks.json")
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], expected["status"])
        self.assertEqual(result["issues"], [])
        value = result["algorithm_input"]
        self.assertEqual([c["candidate_id"] for c in value["candidates"]], expected["candidate_ids"])
        weights = {q["question_id"]: q["weight"] for q in value["scoring_model"]["questions"] if q["weight"] is not None}
        self.assertEqual(weights, expected["question_weights"])
        constraints = {c["participant_id"]: c for c in value["constraints"]}
        self.assertEqual(constraints["p1"]["budget"]["max_cost_minor"], expected["p1_budget_minor"])
        self.assertEqual(constraints["p1"]["required_attributes"], [{"attribute_id": expected["p1_required_attribute"], "required_value": "yes"}])
        self.assertEqual(constraints["p2"]["budget"]["kind"], expected["p2_budget_kind"])
        self.assertIn({"participant_id": "p1", "source_question_id": "q_environment", "kind": "attribute_preference", "attribute_id": expected["p1_preferred_attribute"], "preferred_value": "yes", "utility_rule": "attribute_match_v1"}, value["preferences"])
        self.assertIn({"participant_id": "p2", "source_question_id": "q_environment", "kind": expected["p2_environment_kind"], "utility_rule": "neutral_v1"}, value["preferences"])
        self.assertIn({"participant_id": "p2", "activity_id": "dinner", "rating": expected["p2_dinner_rating"], "kind": "rating", "source_question_id": "q_rating"}, value["preferences"])
        self.assertEqual(value["context"]["option_snapshot_id"], "options-1")
        self.assertEqual(value["context"]["response_snapshot_id"], "responses-1")
        self.assertEqual(value, fixture("expected_algorithm_input.json"))

    def test_no_leader_weights_uses_equal_default(self) -> None:
        for question in self.planning["questions"]:
            question.pop("leader_weight", None)
        model = preprocess(self.planning, self.responses)["algorithm_input"]["scoring_model"]
        soft = [q for q in model["questions"] if q["weight"] is not None]
        self.assertEqual([q["weight"] for q in soft], [0.5, 0.5])
        self.assertTrue(all(q["weight_source"] == "equal_default" for q in soft))

    def test_partial_weights_are_invalid(self) -> None:
        self.planning["questions"][-1].pop("leader_weight")
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["issues"][0]["code"], "PARTIAL_WEIGHTS")

    def test_vague_open_answer_requires_clarification(self) -> None:
        self.responses["participants"][0]["answers"][-1]["value"] = "Somewhere nice"
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIsNone(result["algorithm_input"])
        self.assertIn("UNSUPPORTED_ANSWER", [issue["code"] for issue in result["issues"]])

    def test_missing_roster_member_cannot_be_ignored(self) -> None:
        self.responses["participants"].pop()
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIsNone(result["algorithm_input"])
        self.assertIn("ROSTER_MISMATCH", [issue["code"] for issue in result["issues"]])

    def test_stale_option_revision_is_invalid(self) -> None:
        self.responses["option_revision"] = "old"
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["issues"][0]["code"], "STALE_SNAPSHOT")

    def test_unknown_activity_fact_is_preserved(self) -> None:
        result = preprocess(self.planning, self.responses)
        dinner = next(c for c in result["algorithm_input"]["candidates"] if c["activity_id"] == "dinner")
        self.assertIn({"attribute_id": "vegetarian_option", "value": "unknown"}, dinner["attributes"])

    def test_exactly_overlapping_windows_do_not_duplicate_candidates(self) -> None:
        activity = copy.deepcopy(self.planning["activities"][0])
        activity["windows"].append(copy.deepcopy(activity["windows"][0]))
        candidates = generate_candidates([activity], "1", "Asia/Singapore")
        self.assertEqual(len(candidates), 1)

    def test_unaligned_window_generates_next_grid_start(self) -> None:
        activity = copy.deepcopy(self.planning["activities"][0])
        activity["duration_minutes"] = 60
        activity["windows"] = [{"start_at": "2026-10-02T19:15:00+08:00", "end_at": "2026-10-02T21:00:00+08:00"}]
        candidates = generate_candidates([activity], "1", "Asia/Singapore")
        self.assertEqual([c["start_at"] for c in candidates], ["2026-10-02T11:30:00Z", "2026-10-02T12:00:00Z"])

    def test_full_duration_must_fit_window(self) -> None:
        activity = copy.deepcopy(self.planning["activities"][0])
        activity["windows"] = [{"start_at": "2026-10-02T19:00:00+08:00", "end_at": "2026-10-02T20:30:00+08:00"}]
        self.assertEqual(generate_candidates([activity], "1", "Asia/Singapore"), [])

    def test_budget_open_answer_and_conflict(self) -> None:
        self.planning["questions"].append({"question_id": "q_budget_text", "label": "State your maximum spend", "kind": "open_budget", "required": False})
        answer = {"answer_id": "p1-extra", "question_id": "q_budget_text", "value": "My maximum is SGD 30."}
        self.responses["participants"][0]["answers"].append(answer)
        self.assertEqual(preprocess(self.planning, self.responses)["status"], "ready")
        answer["value"] = "My maximum is SGD 50."
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("CONFLICTING_ANSWER", [issue["code"] for issue in result["issues"]])

    def test_budget_conflict_is_found_regardless_of_question_order(self) -> None:
        self.planning["questions"].insert(0, {"question_id": "q_budget_text", "label": "State your maximum spend", "kind": "open_budget", "required": False})
        self.responses["participants"][0]["answers"].append({"answer_id": "p1-extra", "question_id": "q_budget_text", "value": "My maximum is SGD 50."})
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("CONFLICTING_ANSWER", [issue["code"] for issue in result["issues"]])

    def test_negated_requirement_is_not_added(self) -> None:
        self.responses["participants"][0]["answers"][-2]["value"] = "I don't need vegetarian food."
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["algorithm_input"]["constraints"][0]["required_attributes"], [])

    def test_boolean_rating_is_rejected(self) -> None:
        self.responses["participants"][0]["answers"][2]["value"]["cafe"] = True
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["issues"][0]["code"], "INVALID_VALUE")

    def test_cannot_join_flag_replaces_an_activity_rating(self) -> None:
        self.planning["questions"].append({"question_id": "q_flag", "label": "Any activity you cannot join?", "kind": "candidate_flag", "required": False})
        self.responses["participants"][0]["answers"][2]["value"].pop("dinner")
        self.responses["participants"][0]["answers"].append({"answer_id": "p1-flag", "question_id": "q_flag", "value": [{"activity_id": "dinner", "flag": "cannot_join"}]})
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "ready")
        flags = result["algorithm_input"]["constraints"][0]["candidate_flags"]
        self.assertEqual(flags, [{"candidate_id": "dinner@2026-10-02T11:00:00Z", "flag": "cannot_join"}])

    def test_rating_and_flag_for_same_activity_conflict(self) -> None:
        self.planning["questions"].append({"question_id": "q_flag", "label": "Any activity you cannot join?", "kind": "candidate_flag", "required": False})
        self.responses["participants"][0]["answers"].append({"answer_id": "p1-flag", "question_id": "q_flag", "value": [{"activity_id": "dinner", "flag": "cannot_join"}]})
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("CONFLICTING_ANSWER", [issue["code"] for issue in result["issues"]])

    def test_no_candidate_does_not_make_activity_rating_invalid(self) -> None:
        self.planning["activities"][0]["windows"][0]["end_at"] = "2026-10-02T20:00:00+08:00"
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "ready")
        self.assertEqual([c["activity_id"] for c in result["algorithm_input"]["candidates"]], ["dinner"])

    def test_open_requirement_with_negation_and_requirement_is_ambiguous(self) -> None:
        self.responses["participants"][0]["answers"][-2]["value"] = "I don't need vegetarian food but I must have step-free access."
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("AMBIGUOUS_ANSWER", [issue["code"] for issue in result["issues"]])

    def test_negated_open_preference_preserves_the_opposite_value(self) -> None:
        self.responses["participants"][0]["answers"][-1]["value"] = "I don't want indoors."
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "ready")
        preference = next(p for p in result["algorithm_input"]["preferences"] if p["participant_id"] == "p1" and p["source_question_id"] == "q_environment")
        self.assertEqual((preference["attribute_id"], preference["preferred_value"]), ("indoor", "no"))

    def test_conflicting_open_preference_is_not_guessed(self) -> None:
        self.responses["participants"][0]["answers"][-1]["value"] = "I prefer indoors and outdoors."
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIn("CONFLICTING_ANSWER", [issue["code"] for issue in result["issues"]])


if __name__ == "__main__":
    unittest.main()
