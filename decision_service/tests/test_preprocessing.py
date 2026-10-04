"""Contract and semantic boundary tests using frozen, representative inputs."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from decision_service.preprocessing import preprocess
from decision_service.preprocessing.candidates import generate_candidates
from decision_service.preprocessing.semantics import OllamaSemanticProvider, OpenAISemanticProvider, SemanticServiceError


FIXTURES = Path(__file__).parents[1] / "fixtures" / "preprocessing"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


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
        self.assertEqual(constraints["p1"]["required_attributes"], [{"attribute_id": expected["p1_required_attribute"], "required_value": "yes", "source_question_id": "q_requirement"}])
        self.assertEqual(constraints["p2"]["budget"]["kind"], expected["p2_budget_kind"])
        self.assertIn({"participant_id": "p1", "source_question_id": "q_environment", "kind": "attribute_preference", "attribute_id": expected["p1_preferred_attribute"], "preferred_value": "yes", "utility_rule": "attribute_match_v1"}, value["preferences"])
        self.assertIn({"participant_id": "p2", "source_question_id": "q_environment", "kind": expected["p2_environment_kind"], "utility_rule": "neutral_v1"}, value["preferences"])
        self.assertIn({"participant_id": "p2", "activity_id": "dinner", "rating": expected["p2_dinner_rating"], "kind": "rating", "source_question_id": "q_rating"}, value["preferences"])
        self.assertEqual(value["context"]["option_snapshot_id"], "options-1")
        self.assertEqual(value["context"]["response_snapshot_id"], "responses-1")
        self.assertEqual(value, fixture("expected_algorithm_input.json"))

    def test_no_leader_weights_use_option_relevance(self) -> None:
        for question in self.planning["questions"]:
            question.pop("leader_weight", None)
        model = preprocess(self.planning, self.responses)["algorithm_input"]["scoring_model"]
        soft = [q for q in model["questions"] if q["weight"] is not None]
        self.assertAlmostEqual(soft[0]["weight"], 1 / 1.125)
        self.assertAlmostEqual(soft[1]["weight"], 0.125 / 1.125)
        self.assertTrue(all(q["weight_source"] == "auto_relevance" for q in soft))

    def test_local_model_assesses_every_unweighted_soft_question_and_replays(self) -> None:
        for question in self.planning["questions"]:
            question.pop("leader_weight", None)

        class FakeProvider:
            model = "qwen3:4b-instruct"

            def __init__(self):
                self.calls = []

            def assess_question(self, question, context, candidates):
                self.calls.append((question["question_id"], context["decision_question"]))
                return {
                    "criterion": question["label"],
                    "relevance": 0.2 if question["kind"] == "activity_rating" else 0.8,
                    "reason": "Relevant to the Friday activity choice",
                }

            def extract_answer(self, question, answer_text, context):
                raise AssertionError("Controlled answers should use deterministic extraction")

        provider = FakeProvider()
        result = preprocess(self.planning, self.responses, semantic_provider=provider)
        self.assertEqual(result["status"], "ready")
        self.assertEqual([call[0] for call in provider.calls], ["q_rating", "q_environment"])
        self.assertTrue(all("Friday evening activity" in call[1] for call in provider.calls))
        weights = {q["question_id"]: q for q in result["algorithm_input"]["scoring_model"]["questions"]}
        self.assertEqual((weights["q_rating"]["weight"], weights["q_environment"]["weight"]), (0.2, 0.8))
        self.assertEqual(weights["q_rating"]["weight_source"], "model_relevance")
        self.assertEqual(set(result["semantic_evidence"]["question_assessments"]), {"q_rating", "q_environment"})
        replay = preprocess(self.planning, self.responses, semantic_evidence=result["semantic_evidence"])
        self.assertEqual(replay["status"], "ready")
        self.assertEqual(replay["algorithm_input"], result["algorithm_input"])

    def test_question_relevance_changes_when_options_differ(self) -> None:
        self.planning = fixture("planning_auto_weights.json")
        result = preprocess(self.planning, self.responses)
        questions = {q["question_id"]: q for q in result["algorithm_input"]["scoring_model"]["questions"]}
        self.assertAlmostEqual(questions["q_environment"]["relevance"], 0.5)
        self.assertAlmostEqual(questions["q_environment"]["weight"], 1 / 3)
        self.assertNotIn("question_matches", result["algorithm_input"])

    def test_repeated_soft_topic_does_not_double_automatic_weight(self) -> None:
        self.planning = fixture("planning_auto_weights.json")
        duplicate = copy.deepcopy(self.planning["questions"][-1])
        duplicate["question_id"] = "q_environment_again"
        self.planning["questions"].append(duplicate)
        for member in self.responses["participants"]:
            copied = copy.deepcopy(member["answers"][-1])
            copied["question_id"] = "q_environment_again"
            copied["answer_id"] += "-again"
            member["answers"].append(copied)
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "ready")
        weights = {q["question_id"]: q["weight"] for q in result["algorithm_input"]["scoring_model"]["questions"]}
        self.assertAlmostEqual(weights["q_environment"] + weights["q_environment_again"], 1 / 3)
        self.assertAlmostEqual(weights["q_rating"], 2 / 3)

    def test_partial_leader_weights_use_relevance_for_missing_question(self) -> None:
        self.planning["questions"][-1].pop("leader_weight")
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "ready")
        questions = {q["question_id"]: q for q in result["algorithm_input"]["scoring_model"]["questions"]}
        self.assertEqual(questions["q_rating"]["weight_source"], "leader")
        self.assertEqual(questions["q_environment"]["weight_source"], "auto_relevance")

    def test_hard_question_weight_is_rejected(self) -> None:
        self.planning["questions"][1]["leader_weight"] = 10
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["issues"][0]["code"], "HARD_WEIGHT_UNSUPPORTED")

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
        self.assertNotIn("question_matches", result["algorithm_input"])

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
        self.assertEqual(flags, [{"candidate_id": "dinner@2026-10-02T11:00:00Z", "flag": "cannot_join", "source_question_id": "q_flag"}])

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

    def test_generic_text_and_choice_questions_use_semantic_provider(self) -> None:
        class FakeProvider:
            model = "fake-v1"

            def assess_question(self, question, context, candidates):
                return {"criterion": "accessibility" if question["kind"] == "semantic_requirement" else "travel convenience", "relevance": 0.75, "reason": "Option descriptions provide relevant facts"}

            def extract_answer(self, question, answer_text, context):
                is_hard = question["kind"] == "semantic_requirement"
                return {
                    "status": "resolved",
                    "criterion": "accessibility" if is_hard else "travel convenience",
                    "value": "ramp_required" if is_hard else "walkable",
                    "meaning": answer_text,
                    "evidence": answer_text,
                }

        self.planning["activities"][0]["description"] = "Ramp available; five minute walk from the station."
        self.planning["activities"][1]["description"] = "Stairs only; thirty minute drive."
        self.planning["questions"].extend([
            {"question_id": "q_access", "label": "What access do you need?", "kind": "semantic_requirement", "answer_format": "text"},
            {"question_id": "q_travel", "label": "How would you like to travel?", "kind": "semantic_preference", "answer_format": "choice", "choices": [{"choice_id": "walk", "label": "Walkable"}, {"choice_id": "drive", "label": "Driving is fine"}]},
        ])
        for member in self.responses["participants"]:
            member["answers"].extend([
                {"answer_id": member["participant_id"] + "-access", "question_id": "q_access", "value": "I need a ramp"},
                {"answer_id": member["participant_id"] + "-travel", "question_id": "q_travel", "value": {"choice_id": "walk"}},
            ])
        result = preprocess(self.planning, self.responses, semantic_provider=FakeProvider())
        self.assertEqual(result["status"], "ready")
        value = result["algorithm_input"]
        self.assertEqual(value["context"]["semantic_model"], "fake-v1")
        questions = {q["question_id"]: q for q in value["scoring_model"]["questions"]}
        self.assertEqual(questions["q_travel"]["weight_source"], "model_relevance")
        self.assertEqual(questions["q_access"]["weight"], None)
        self.assertIn({"participant_id": "p1", "question_id": "q_travel", "kind": "semantic_preference", "status": "resolved", "criterion": "travel convenience", "value": "walkable", "meaning": "Walkable", "evidence": "Walkable"}, value["semantic_interpretations"])
        self.assertNotIn("question_matches", value)
        replay = preprocess(self.planning, self.responses, semantic_evidence=result["semantic_evidence"])
        self.assertEqual(replay["status"], "ready")
        self.assertEqual(replay["algorithm_input"], value)
        self.assertEqual(replay["semantic_evidence"], result["semantic_evidence"])
        self.assertEqual(len(value["context"]["semantic_artifact_id"]), 64)

        stale_evidence = copy.deepcopy(result["semantic_evidence"])
        stale_evidence["response_snapshot_id"] = "different"
        stale = preprocess(self.planning, self.responses, semantic_evidence=stale_evidence)
        self.assertEqual(stale["status"], "invalid_input")
        self.assertEqual(stale["issues"][0]["code"], "STALE_SEMANTIC_EVIDENCE")

    def test_generic_question_without_provider_needs_clarification(self) -> None:
        self.planning["questions"].append({"question_id": "q_music", "label": "What music do you enjoy?", "kind": "semantic_preference"})
        for member in self.responses["participants"]:
            member["answers"].append({"answer_id": member["participant_id"] + "-music", "question_id": "q_music", "value": "Acoustic music"})
        result = preprocess(self.planning, self.responses)
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(result["issues"][0]["code"], "SEMANTIC_PROVIDER_REQUIRED")

    def test_reviewed_semantic_fixture_replays_offline(self) -> None:
        result = preprocess(
            fixture("planning_semantic.json"),
            fixture("response_semantic.json"),
            semantic_evidence=fixture("semantic_evidence.json"),
        )
        self.assertEqual(result["status"], "ready")
        value = result["algorithm_input"]
        travel = next(q for q in value["scoring_model"]["questions"] if q["question_id"] == "q_travel")
        self.assertEqual((travel["weight"], travel["weight_source"], travel["relevance"]), (1.0, "model_relevance", 0.75))
        self.assertEqual(len(value["semantic_interpretations"]), 4)
        access = next(i for i in value["semantic_interpretations"] if i["participant_id"] == "p1" and i["question_id"] == "q_access")
        self.assertEqual((access["value"], access["evidence"]), ("ramp_required", "I need a ramp"))
        self.assertNotIn("question_matches", value)

    def test_unresolved_semantic_answer_blocks_matcher_handoff(self) -> None:
        evidence = fixture("semantic_evidence.json")
        evidence["answer_assessments"]["p1"]["q_access"] = {
            "status": "unresolved", "criterion": "", "value": "",
            "meaning": "Access need is unclear", "evidence": "",
        }
        result = preprocess(
            fixture("planning_semantic.json"),
            fixture("response_semantic.json"),
            semantic_evidence=evidence,
        )
        self.assertEqual(result["status"], "needs_clarification")
        self.assertIsNone(result["algorithm_input"])
        self.assertIn("AMBIGUOUS_ANSWER", [issue["code"] for issue in result["issues"]])

    def test_model_result_requires_typed_meaning(self) -> None:
        class BadProvider:
            def assess_question(self, question, context, candidates):
                return {"criterion": "music", "relevance": 0.8, "reason": "Options differ in music"}

            def extract_answer(self, question, answer_text, context):
                return {"status": "resolved", "criterion": "", "value": "acoustic", "meaning": "likes acoustic music", "evidence": "Acoustic music"}

        self.planning["questions"].append({"question_id": "q_music", "label": "What music do you enjoy?", "kind": "semantic_preference"})
        for member in self.responses["participants"]:
            member["answers"].append({"answer_id": member["participant_id"] + "-music", "question_id": "q_music", "value": "Acoustic music"})
        result = preprocess(self.planning, self.responses, semantic_provider=BadProvider())
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["issues"][0]["code"], "INVALID_SEMANTIC_RESULT")

    def test_model_extraction_without_answer_evidence_is_rejected(self) -> None:
        class UngroundedProvider:
            def assess_question(self, question, context, candidates):
                return {"criterion": "music", "relevance": 0.8, "reason": "Options differ in music"}

            def extract_answer(self, question, answer_text, context):
                return {"status": "resolved", "criterion": "music", "value": "acoustic", "meaning": "likes acoustic music", "evidence": "live acoustic band"}

        self.planning["questions"].append({"question_id": "q_music", "label": "What music do you enjoy?", "kind": "semantic_preference"})
        for member in self.responses["participants"]:
            member["answers"].append({"answer_id": member["participant_id"] + "-music", "question_id": "q_music", "value": "Acoustic music"})
        result = preprocess(self.planning, self.responses, semantic_provider=UngroundedProvider())
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["issues"][0]["code"], "UNGROUNDED_SEMANTIC_RESULT")

    def test_openai_adapter_uses_structured_response_request(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, *args):
                return json.dumps({"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"criterion": "music", "relevance": 0.7, "reason": "Options differ"})}]}]}).encode()

        provider = OpenAISemanticProvider(model="test-model", api_key="test-key")
        with patch("decision_service.preprocessing.semantics.urlopen", return_value=FakeResponse()) as mocked:
            result = provider.assess_question({"label": "Music?", "kind": "semantic_preference", "choices": {}}, {}, [])
        self.assertEqual(result["relevance"], 0.7)
        request = mocked.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertIs(body["store"], False)

    def test_ollama_adapter_uses_local_structured_chat(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, *args):
                return json.dumps({"done": True, "message": {"content": json.dumps({"criterion": "venue", "relevance": 0.7, "reason": "Useful to the decision"})}}).encode()

        provider = OllamaSemanticProvider(base_url="http://ollama:11434")
        with patch("decision_service.preprocessing.semantics.urlopen", return_value=FakeResponse()) as mocked:
            result = provider.assess_question({"label": "Venue?", "kind": "open_preference", "supported_attributes": ["quiet"]}, {"decision_question": "Where should we go?"}, [])
        self.assertEqual(result["relevance"], 0.7)
        request = mocked.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "http://ollama:11434/api/chat")
        self.assertEqual(body["model"], "qwen3:4b-instruct")
        self.assertIs(body["stream"], False)
        self.assertEqual(body["format"]["required"], ["criterion", "relevance", "reason"])
        self.assertEqual(json.loads(body["messages"][1]["content"])["context"]["decision_question"], "Where should we go?")
        self.assertEqual(json.loads(body["messages"][1]["content"])["question"]["supported_attributes"], ["quiet"])

    def test_ollama_adapter_reports_unavailable_server(self) -> None:
        provider = OllamaSemanticProvider()
        with patch("decision_service.preprocessing.semantics.urlopen", side_effect=TimeoutError):
            with self.assertRaises(SemanticServiceError):
                provider.assess_question({"label": "Venue?", "kind": "open_preference"}, {}, [])

    def test_ollama_answer_schema_extracts_meaning_without_candidates(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, *args):
                return json.dumps({"done": True, "message": {"content": json.dumps({"status": "resolved", "criterion": "accessibility", "value": "ramp_required", "meaning": "Needs a ramp", "evidence": "I need a ramp"})}}).encode()

        provider = OllamaSemanticProvider()
        with patch("decision_service.preprocessing.semantics.urlopen", return_value=FakeResponse()) as mocked:
            provider.extract_answer({"label": "Access?", "kind": "semantic_requirement"}, "I need a ramp", {})
        body = json.loads(mocked.call_args.args[0].data)
        self.assertEqual(body["format"]["required"], ["status", "criterion", "value", "meaning", "evidence"])
        self.assertNotIn("candidates", json.loads(body["messages"][1]["content"]))


if __name__ == "__main__":
    unittest.main()
