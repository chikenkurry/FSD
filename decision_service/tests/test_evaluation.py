"""Verify evaluation detects errors without leaking gold labels to extraction."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from decision_service.evaluation import evaluate, load_dataset
from decision_service.evaluation.runner import check_assertion, validate_dataset


ROOT = Path(__file__).parents[2]
DATASET = ROOT / "decision_service" / "fixtures" / "evaluation" / "cases.json"


def assertion(value, op="rows", path="/rows"):
    return {"dimension": "extraction", "path": path, "op": op, "value": value}


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.dataset = load_dataset(DATASET)

    def one_case(self, case_id="purchase-typed-values"):
        dataset = copy.deepcopy(self.dataset)
        dataset["cases"] = [next(case for case in dataset["cases"] if case["case_id"] == case_id)]
        return dataset

    def test_structured_corpus_runs_across_domains_without_model(self):
        report = evaluate(self.dataset, tags=("structured",))
        self.assertEqual(report["cases"]["passed"], 12)
        self.assertEqual(report["cases"]["total"], 12)
        self.assertEqual(report["operational_errors"], 0)
        self.assertEqual(set(report["by_domain"]), {"purchase", "trip", "event", "project"})
        self.assertEqual(report["assertions"]["accuracy"], 1)

    def test_rules_failures_on_semantic_cases_are_visible(self):
        report = evaluate(self.dataset, tags=("semantic",))
        self.assertEqual(report["cases"]["total"], 6)
        self.assertLess(report["cases"]["passed"], 6)
        self.assertEqual(report["operational_errors"], 0)
        self.assertTrue(any(case["failures"] for case in report["results"]))
        self.assertIn("classification", report["by_dimension"])

    def test_extra_hard_constraint_or_missing_preference_fails_exact_rows(self):
        check = check_assertion({"rows": [{"criterion": "budget"}, {"criterion": "access"}]},
                                assertion([{"criterion": "budget"}]))
        self.assertFalse(check["passed"])
        self.assertEqual(check["unexpected_rows"], [{"criterion": "access"}])
        check = check_assertion({"rows": []}, assertion([{"polarity": "avoid"}]))
        self.assertEqual(check["missing_rows"], [{"polarity": "avoid"}])

    def test_partial_rows_ignore_order_and_extra_fields_but_not_extra_rows(self):
        actual = {"rows": [{"id": "b", "value": 2}, {"id": "a", "value": 1}]}
        self.assertTrue(check_assertion(actual, assertion([{"id": "a"}, {"id": "b"}]))["passed"])
        self.assertTrue(check_assertion(actual, assertion([{"id": "a"}], "contains_rows"))["passed"])
        self.assertTrue(check_assertion(actual, assertion([{"id": "c"}], "absent_rows"))["passed"])
        self.assertFalse(check_assertion(actual, assertion([{"id": "b"}], "absent_rows"))["passed"])

    def test_overlapping_labels_use_distinct_rows_with_complete_assignment(self):
        actual = {"rows": [{"id": "a", "value": 1}, {"id": "b", "value": 1}]}
        self.assertTrue(check_assertion(actual, assertion([{"value": 1}, {"id": "a"}]))["passed"])
        self.assertFalse(check_assertion({"rows": [{"id": "a"}]}, assertion([{"id": "a"}, {"id": "a"}]))["passed"])

    def test_missing_paths_boolean_types_and_weight_tolerance(self):
        missing = check_assertion({}, assertion(None, "equals", "/absent"))
        self.assertFalse(missing["passed"])
        self.assertTrue(missing["missing_path"])
        self.assertFalse(check_assertion({"rows": True}, assertion(1, "equals"))["passed"])
        self.assertTrue(check_assertion({"rows": 0.333333333333}, assertion(1/3, "approx"))["passed"])
        self.assertFalse(check_assertion({"rows": 0.34}, assertion(1/3, "approx"))["passed"])
        self.assertTrue(check_assertion({"a/b": {"~": 1}}, assertion(1, "equals", "/a~1b/~0"))["passed"])
        self.assertFalse(check_assertion({"rows": [1]}, assertion(1, "equals", "/rows/-1"))["passed"])

    def test_bad_labels_duplicate_ids_and_empty_selection_are_rejected(self):
        for change in ("duplicate", "empty", "operator", "dimension", "pointer", "rows"):
            with self.subTest(change=change):
                dataset = self.one_case()
                case = dataset["cases"][0]
                if change == "duplicate":
                    dataset["cases"].append(copy.deepcopy(case))
                elif change == "empty":
                    case["assertions"] = []
                elif change == "operator":
                    case["assertions"][0]["op"] = "invented"
                elif change == "dimension":
                    case["assertions"][0]["dimension"] = []
                elif change == "pointer":
                    case["assertions"][0]["path"] = "/invalid~3escape"
                else:
                    case["assertions"][2]["value"] = [{}]
                with self.assertRaises(ValueError):
                    validate_dataset(dataset)
        with self.assertRaises(ValueError):
            evaluate(self.dataset, tags=("not-a-tag",))

    def test_nonfinite_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"value": NaN}')
            with self.assertRaises(ValueError):
                load_dataset(path)

    def test_auto_weights_are_normalized_without_requiring_equal_relevance(self):
        check = {"dimension": "weights", "path": "/rows", "op": "normalized_weights", "value": ["a", "b"]}
        actual = {"rows": [{"question_id": "a", "role": "soft", "weight": 0.8},
                           {"question_id": "b", "role": "soft", "weight": 0.2},
                           {"question_id": "c", "role": "hard", "weight": None}]}
        self.assertTrue(check_assertion(actual, check)["passed"])
        for value in (0.3, True, float("nan"), -0.2):
            actual["rows"][1]["weight"] = value
            self.assertFalse(check_assertion(actual, check)["passed"])

    def test_rejected_model_reply_and_validation_issue_are_retained(self):
        class Provider:
            model = "invalid-role-provider"

            def classify_question(self, question, context):
                return {"role": "invented", "criterion": "battery_life", "relevance": 1, "reason": "Bad role"}

        report = evaluate(self.one_case("purchase-runtime-paraphrase"), semantic_provider=Provider())
        case = report["results"][0]
        self.assertEqual(case["result_status"], "invalid_input")
        self.assertTrue(case["issues"])
        self.assertEqual(case["model_calls"][0]["response"]["role"], "invented")
        self.assertGreater(case["metrics"]["missing_paths"], 0)

    def test_preprocessor_receives_snapshots_without_gold_labels_and_cannot_mutate_dataset(self):
        dataset = self.one_case()
        original = copy.deepcopy(dataset)

        def process(planning, responses, **kwargs):
            self.assertNotIn("assertions", planning)
            self.assertNotIn("assertions", responses)
            planning.clear()
            responses.clear()
            return {}

        with patch("decision_service.evaluation.runner.preprocess", side_effect=process):
            report = evaluate(dataset)
        self.assertEqual(dataset, original)
        self.assertEqual(report["cases"]["passed"], 0)

    def test_execution_errors_remain_in_denominator_and_do_not_stop_other_cases(self):
        dataset = self.one_case()
        second = copy.deepcopy(dataset["cases"][0])
        second["case_id"] = "second-case"
        dataset["cases"].append(second)
        with patch("decision_service.evaluation.runner.preprocess", side_effect=[RuntimeError("private data"), {}]):
            report = evaluate(dataset)
        self.assertEqual(report["cases"]["total"], 2)
        self.assertEqual(report["operational_errors"], 1)
        self.assertEqual(report["cases"]["passed"], 0)
        self.assertNotIn("private data", json.dumps(report))

    def test_provider_unavailable_is_an_operational_failure(self):
        with patch("decision_service.evaluation.runner.preprocess", return_value={"status": "upstream_unavailable"}):
            report = evaluate(self.one_case())
        self.assertEqual(report["operational_errors"], 1)
        self.assertEqual(report["cases"]["passed"], 0)

    def test_live_evidence_can_be_saved_and_replayed_without_model(self):
        class Provider:
            model = "test-provider"

            def extract_sparse_answer(self, question, answer_text, context):
                return {"status": "resolved", "interpretations": [
                    {"criterion": "environment", "value": "indoor", "evidence": "indoor", "must_have": False, "polarity": "prefer"},
                    {"criterion": "environment", "value": "noisy", "evidence": "avoid noisy", "must_have": False, "polarity": "avoid"},
                ]}

        dataset = self.one_case("event-prefer-and-avoid")
        with tempfile.TemporaryDirectory() as directory:
            live = evaluate(dataset, semantic_provider=Provider(), save_evidence_dir=Path(directory))
            replay = evaluate(dataset, evidence_dir=Path(directory))
            self.assertEqual(live["cases"]["passed"], 1)
            self.assertIn("EXECUTION_ADAPTER_REQUIRED", [issue["code"] for issue in live["results"][0]["issues"]])
            self.assertIsNone(live["results"][0]["error"])
            self.assertEqual(replay["cases"], live["cases"])
            self.assertEqual(replay["assertions"], live["assertions"])
            self.assertEqual(replay["mode"], "replay")
            self.assertEqual(replay["results"][0]["evidence_model"], "test-provider")
            self.assertEqual(replay["dataset_sha256"], live["dataset_sha256"])
            with self.assertRaises(ValueError):
                evaluate(dataset, semantic_provider=Provider(), evidence_dir=Path(directory))

    def test_missing_replay_file_is_a_failed_case_without_rules_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            report = evaluate(self.one_case(), evidence_dir=Path(directory))
        self.assertEqual(report["cases"]["passed"], 0)
        self.assertEqual(report["operational_errors"], 1)

    def test_hybrid_run_saves_rules_cases_for_full_replay(self):
        class Provider:
            model = "must-not-be-needed"

            def classify_question(self, *args):
                raise AssertionError("All selected cases are resolved by rules")

        dataset = self.one_case()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            live = evaluate(dataset, semantic_provider=Provider(), save_evidence_dir=path)
            self.assertEqual(live["cases"]["passed"], 1)
            self.assertIn("EXECUTION_ADAPTER_REQUIRED", [issue["code"] for issue in live["results"][0]["issues"]])
            self.assertIsNone(live["results"][0]["error"])
            self.assertEqual(live["results"][0]["model_calls"], [])
            replay = evaluate(dataset, evidence_dir=path)
            self.assertEqual(replay["cases"], live["cases"])
            self.assertIsNone(replay["results"][0]["evidence_model"])

    def test_cli_exit_codes_distinguish_success_failures_and_bad_configuration(self):
        for args, expected in ((["--tag", "structured"], 0), ([], 1), (["--tag", "not-a-tag"], 2)):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, "-m", "decision_service.evaluation", *args],
                                        cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)
                if expected != 2:
                    self.assertEqual(json.loads(result.stdout)["mode"], "rules")


if __name__ == "__main__":
    unittest.main()
