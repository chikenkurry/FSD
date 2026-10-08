"""Money precision, duration bounds and scenario limits across processing paths."""

import unittest

from decision_service.preprocessing import preprocess
from decision_service.preprocessing.common import InputError
from decision_service.preprocessing.extractors import extract_budget
from decision_service.preprocessing.money import parse_amount
from decision_service.preprocessing.scenarios import build_scenario_requests
from decision_service.tests.test_generic_preprocessing import fixture
from decision_service.tests.test_preference_semantics import snapshots


class MoneyTests(unittest.TestCase):
    def test_legacy_budget_uses_supplied_currency_instead_of_sgd_only(self):
        for text, currency, expected in (("My maximum is USD 30.", "USD", 3000),
                                         ("I can spend €25.50", "EUR", 2550),
                                         ("My limit is GBP 2k", "GBP", 200000),
                                         ("My limit is S$30", "SGD", 3000)):
            with self.subTest(currency=currency):
                self.assertEqual(extract_budget(text, currency),
                                 {"kind": "limited", "max_cost_minor": expected, "currency": currency})

    def test_minor_units_are_declared_and_never_rounded(self):
        self.assertEqual(extract_budget("JPY 1200", "JPY", minor_digits=0)["max_cost_minor"], 1200)
        self.assertEqual(extract_budget("BHD 1.234", "BHD", minor_digits=3)["max_cost_minor"], 1234)
        with self.assertRaises(InputError):
            extract_budget("USD 1.234", "USD")

    def test_amounts_are_exact_even_beyond_decimal_context_precision(self):
        value = "123456789012345678901234567890.123456789k USD"
        self.assertEqual(parse_amount(value, "USD", "test"), "123456789012345678901234567890123.456789")

    def test_invalid_grouping_currency_and_compound_budgets_are_rejected(self):
        for text in ("$1,00", "€20", "$20 EUR", "USD 10 or USD 20", "unlimited but USD 20", "not unlimited"):
            with self.subTest(text=text), self.assertRaises(InputError):
                extract_budget(text, "USD")

    def test_currency_code_prefix_suffix_and_k_are_consistent(self):
        for text in ("USD 2000", "USD2000", "2000USD", "$2k", "2k USD"):
            with self.subTest(text=text):
                self.assertEqual(parse_amount(text, "USD", "test"), "2000")

    def test_activity_handoff_carries_declared_minor_unit_precision(self):
        planning = fixture("planning_snapshot.json")
        responses = fixture("response_snapshot.json")
        planning["currency"] = "JPY"
        planning["currency_minor_digits"] = 0
        for activity in planning["activities"]:
            activity["currency"] = "JPY"
        for participant in responses["participants"]:
            for answer in participant["answers"]:
                if isinstance(answer["value"], dict) and "currency" in answer["value"]:
                    answer["value"]["currency"] = "JPY"
        for answer in responses["participants"][1]["answers"]:
            if isinstance(answer["value"], dict) and answer["value"].get("kind") == "unlimited":
                answer["value"] = {"kind": "limited", "currency": "JPY", "max_cost_minor": 5000}
        planning["questions"].append({"question_id": "budget_text", "label": "Maximum spend?", "kind": "open_budget", "required": False})
        responses["participants"][1]["answers"].append({"answer_id": "new-budget", "question_id": "budget_text", "value": "JPY 5000"})
        result = preprocess(planning, responses)
        self.assertEqual(result["status"], "ready", result["issues"])
        self.assertEqual(result["algorithm_input"]["context"]["currency_minor_digits"], 0)
        self.assertEqual(result["algorithm_input"]["constraints"][1]["budget"]["max_cost_minor"], 5000)


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [{"option_id": "option-a"}]
        self.questions = [{"criterion": "duration_days", "choices": {"year": "400 days"}}]
        self.constraints = [{"participant_id": "p1", "criterion": "availability", "value": [
            {"start_date": "2027-01-01", "end_date": "2028-12-31"}]}]

    def test_long_durations_are_limited_by_availability_not_365_days(self):
        result = build_scenario_requests(self.candidates, ["p1"], self.constraints, [], self.questions)
        self.assertEqual(result[0]["duration_days"], 400)

    def test_large_duration_range_is_clipped_before_enumeration(self):
        preferences = [{"criterion": "duration_days", "intent": "range", "value": {
            "lower": 1, "upper": 10**20, "lower_inclusive": True, "upper_inclusive": True}}]
        result = build_scenario_requests(self.candidates, ["p1"], self.constraints, preferences, [], max_requests=1000)
        self.assertEqual(len(result), 731)

    def test_request_limit_checks_option_window_product(self):
        candidates = self.candidates + [{"option_id": "option-b"}]
        with self.assertRaises(InputError) as error:
            build_scenario_requests(candidates, ["p1"], self.constraints, [], self.questions, max_requests=1)
        self.assertEqual(error.exception.code, "LIMIT_EXCEEDED")

    def test_open_range_endpoints_and_duplicate_windows_are_preserved(self):
        self.constraints[0]["value"] *= 2
        preferences = [{"criterion": "duration_days", "intent": "range", "value": {
            "lower": 2, "upper": 4, "lower_inclusive": False, "upper_inclusive": False}}]
        result = build_scenario_requests(self.candidates, ["p1"], self.constraints, preferences, [])
        self.assertEqual([r["duration_days"] for r in result], [3])

    def test_year_plus_member_target_compiles_and_fractional_target_requests_review(self):
        planning, responses = snapshots([("duration_days", "number", "days")],
                                        [{"duration_days": 400}, {"duration_days": 500}],
                                        {"question_id": "duration", "label": "Ideal duration in days?"})
        responses["participants"][0]["answers"][0]["value"] = "400 days"
        result = preprocess(planning, responses)
        self.assertEqual(result["preparation"]["status"], "ready", result["issues"])
        responses["participants"][0]["answers"][0]["value"] = "400.5 days"
        self.assertEqual(preprocess(planning, responses)["status"], "needs_clarification")

    def test_scenario_limit_configuration_is_validated(self):
        for limit in (0, -1, True, "100"):
            with self.subTest(limit=limit):
                self.assertEqual(preprocess(fixture("planning_generic.json"), fixture("response_generic.json"),
                                            policy={"max_scenario_requests": limit})["status"], "invalid_input")

    def test_replay_rejects_a_changed_scenario_policy(self):
        planning = fixture("planning_generic.json")
        responses = fixture("response_generic.json")
        planning["questions"] = [{"question_id": "battery", "label": "Desired unplugged runtime?", "numeric_intent": "target"}]
        responses["participants"][0]["answers"] = [{"question_id": "battery", "value": "12 hours"}]
        class Provider:
            model = "policy-test"
            def classify_question(self, question, context):
                return {"role": "soft", "criterion": "battery_life", "relevance": 1, "reason": "Runtime"}
        original = preprocess(planning, responses, semantic_provider=Provider(), policy={"max_scenario_requests": 20})
        result = preprocess(planning, responses, semantic_evidence=original["semantic_evidence"],
                            policy={"max_scenario_requests": 21})
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["issues"][0]["code"], "STALE_SEMANTIC_EVIDENCE")

    def test_resource_limit_is_an_actionable_processing_issue(self):
        planning, responses = snapshots([("duration_days", "number", "days")],
                                        [{"duration_days": 2}, {"duration_days": 4}],
                                        {"question_id": "duration", "label": "Ideal duration in days?"})
        planning["questions"].append({"question_id": "dates", "label": "When is your availability?"})
        responses["participants"][0]["answers"] = [
            {"question_id": "duration", "value": "between 2 and 4 days"},
            {"question_id": "dates", "value": "2027-01-01 to 2027-01-10"}]
        result = preprocess(planning, responses, policy={"max_scenario_requests": 1})
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["issues"][0]["code"], "LIMIT_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
