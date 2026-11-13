"""compile_answers: several picks on one question, and declining a boolean requirement.

These cover two real organiser forms that used to fail. A multiple-choice question
mapped to a single-value category criterion let members tick more than one option
("Italian or Japanese"), which compile_answers read as a contradiction instead of
"either satisfies me". And answering "No" to a yes/no requirement ("Do you need a
halal option?") was read as "options must NOT be halal" instead of "no requirement".
"""

from __future__ import annotations

import unittest

from decision_service.preprocessing.generic_preparation import compile_answers


def question(role: str, attribute_id: str, value_type: str, comparison_rule: str, unit: str | None = None) -> dict:
    return {"role": role, "mapping": {"status": "resolved", "attribute_id": attribute_id,
                                       "value_type": value_type, "comparison_rule": comparison_rule, "unit": unit}}


def pick(member_id: str, qid: str, criterion: str, value: object, *, polarity: str = "prefer") -> dict:
    """One normalized answer entry, shaped as compile_answers expects it."""
    return {
        "participant_id": member_id, "question_id": qid, "criterion": criterion, "value": value, "polarity": polarity,
        "provenance": {"participant_id": member_id, "source_question_id": qid,
                       "source_answer_id": f"resp:{member_id}:{qid}", "source_type": "member_response", "evidence": str(value)},
        "confirmation": None,
    }


class MultiplePicksOnOneQuestionTests(unittest.TestCase):
    def test_two_picks_on_a_soft_category_preference_are_scored_as_any_of_them(self):
        questions = {"cuisine": question("soft", "cuisine", "category", "attribute_match_v1")}
        entries = [pick("m1", "cuisine", "cuisine", "Italian"), pick("m1", "cuisine", "cuisine", "Japanese")]
        issues: list[dict] = []
        result = compile_answers(entries, questions, False, issues)
        self.assertEqual(issues, [])
        self.assertEqual(sorted(r["preferred_value"] for r in result), ["italian", "japanese"])
        self.assertTrue(all(r["attribute_id"] == "cuisine" and r["utility_rule"] == "attribute_match_v1" for r in result))

    def test_a_single_pick_is_unaffected(self):
        questions = {"cuisine": question("soft", "cuisine", "category", "attribute_match_v1")}
        result = compile_answers([pick("m1", "cuisine", "cuisine", "Italian")], questions, False, [])
        self.assertEqual([r["preferred_value"] for r in result], ["italian"])

    def test_two_picks_on_a_hard_category_requirement_still_conflict(self):
        questions = {"diet": question("hard", "diet", "category", "equals_v1")}
        entries = [pick("m1", "diet", "diet", "vegetarian"), pick("m1", "diet", "diet", "vegan")]
        issues: list[dict] = []
        result = compile_answers(entries, questions, True, issues)
        self.assertEqual(result, [])
        self.assertEqual([i["code"] for i in issues], ["CONFLICTING_ANSWER"])

    def test_two_picks_on_a_soft_numeric_preference_still_conflict(self):
        # Multiple values only make sense as "any of" for a one-value category pick;
        # a numeric target with two different numbers is still a real contradiction.
        questions = {"budget_wish": question("soft", "budget_wish", "decimal", "numeric_target_v1", unit="SGD")}
        entries = [pick("m1", "budget_wish", "budget_wish", "20"), pick("m1", "budget_wish", "budget_wish", "40")]
        issues: list[dict] = []
        result = compile_answers(entries, questions, False, issues)
        self.assertEqual(result, [])
        self.assertEqual([i["code"] for i in issues], ["CONFLICTING_ANSWER"])


class BooleanRequirementDeclineTests(unittest.TestCase):
    def test_declining_a_boolean_requirement_removes_it_instead_of_requiring_the_opposite(self):
        questions = {"halal": question("hard", "halal", "boolean", "equals_v1")}
        issues: list[dict] = []
        result = compile_answers([pick("m1", "halal", "halal", False)], questions, True, issues)
        self.assertEqual(issues, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["kind"], "unlimited")
        self.assertNotIn("required_value", result[0])

    def test_accepting_a_boolean_requirement_still_requires_the_fact(self):
        questions = {"halal": question("hard", "halal", "boolean", "equals_v1")}
        result = compile_answers([pick("m1", "halal", "halal", True)], questions, True, [])
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0]["required_value"], result[0]["constraint_rule"]), (True, "equals_v1"))

    def test_a_soft_boolean_preference_is_unaffected_by_declining(self):
        # The "No means no requirement" rule is scoped to organiser-declared hard
        # questions; a soft boolean preference keeps its ordinary False value.
        questions = {"loud": question("soft", "loud", "boolean", "attribute_match_v1")}
        result = compile_answers([pick("m1", "loud", "loud", False)], questions, False, [])
        self.assertEqual(result[0]["preferred_value"], False)
