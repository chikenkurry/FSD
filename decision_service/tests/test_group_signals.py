"""Direct option ratings, per-question importance, meaning similarity and early close."""

from copy import deepcopy
import unittest

from decision_service.service.snapshots import SnapshotError
from decision_service.service.views import recommendation_view
from decision_service.service.workflow import execute


def soft(question_id, criterion, **extra):
    return {"question_id": question_id, "label": question_id.title(), "role": "soft", "criterion": criterion,
            "relevance": 1, "required": True, "answer_format": "text",
            "mapping": {"value_type": "category", "comparison_rule": "attribute_match_v1"}, **extra}


def snapshots(questions, answers, options=None, statuses=None):
    """Planning and Participation snapshots shaped like the published app's."""
    members = sorted(answers)
    options = options or [
        {"option_id": "a", "title": "Ramen counter", "facts": [
            {"criterion": "cuisine", "value": "ramen", "value_type": "category", "status": "confirmed", "source": "menu"},
            {"criterion": "vibe", "value": "lively", "value_type": "category", "status": "confirmed", "source": "reviews"}]},
        {"option_id": "b", "title": "Pizza bar", "facts": [
            {"criterion": "cuisine", "value": "italian", "value_type": "category", "status": "confirmed", "source": "menu"},
            {"criterion": "vibe", "value": "quiet", "value_type": "category", "status": "confirmed", "source": "reviews"}]},
    ]
    planning = {"schema_version": "planning-snapshot-v1", "plan_id": "plan-1", "round_id": "round-1", "option_revision": 1,
                "option_snapshot_id": "options-1", "decision_question": "Where should we eat?", "currency": "SGD",
                "currency_minor_digits": 2, "cost_scope": "per_person_total", "interpretation_policy": "facts-v1",
                "roster": members, "questions": questions, "options": options}
    responses = {"schema_version": "response-snapshot-v2", "plan_id": "plan-1", "round_id": "round-1", "option_revision": 1,
                 "option_snapshot_id": "options-1", "snapshot_id": "responses-1", "currency": "SGD", "minor_digits": 2,
                 "participants": [{"participant_id": m, "response_status": (statuses or {}).get(m, "complete"),
                                   "is_required_for_decision": (statuses or {}).get(m, "complete") == "complete" or not statuses,
                                   "answers": answers[m]} for m in members],
                 "constraints": [{"participant_id": m} for m in members]}
    return planning, responses


def winner(run):
    return run["result"]["ranked_candidates"][0]["option_id"]


class OptionRatingTests(unittest.TestCase):
    def test_direct_ratings_rank_the_options_members_prefer(self):
        rate = {"question_id": "rate", "label": "Rate each option", "role": "soft", "criterion": "option_rating",
                "relevance": 1, "required": True, "answer_format": "option_rating"}
        plan, replies = snapshots([rate], {"m1": [{"question_id": "rate", "value": {"a": 1, "b": 4}}],
                                           "m2": [{"question_id": "rate", "value": {"a": 2, "b": 3}}]})
        run = execute(plan, replies)
        self.assertEqual(run["status"], "ranked", run.get("issues"))
        self.assertEqual(winner(run), "b")
        best = run["result"]["ranked_candidates"][0]
        self.assertAlmostEqual(best["average_member_score"], (1 + .75) / 2)
        self.assertAlmostEqual(best["min_member_score"], .75)

    def test_unrated_options_stay_neutral_and_invalid_ratings_need_clarification(self):
        rate = {"question_id": "rate", "label": "Rate each option", "role": "soft", "criterion": "option_rating",
                "relevance": 1, "required": True, "answer_format": "option_rating"}
        plan, replies = snapshots([rate], {"m1": [{"question_id": "rate", "value": {"a": 1}}]})
        run = execute(plan, replies)
        self.assertEqual(winner(run), "b")  # 0.5 neutral beats a's 0.25
        for bad in ({"a": 5}, {"zzz": 2}, {"a": 1.5}, {}):
            plan, replies = snapshots([rate], {"m1": [{"question_id": "rate", "value": bad}]})
            self.assertNotEqual(execute(plan, replies)["status"], "ranked", bad)

    def test_rating_format_and_criterion_must_agree(self):
        mismatched = {"question_id": "rate", "label": "Rate", "role": "soft", "criterion": "option_rating",
                      "relevance": 1, "answer_format": "text"}
        plan, replies = snapshots([mismatched], {"m1": [{"question_id": "rate", "value": "a"}]})
        self.assertEqual(execute(plan, replies)["status"], "invalid_input")


class ImportanceScaleTests(unittest.TestCase):
    def answers(self, cuisine=None, vibe=None):
        return {"m1": [{"question_id": "cuisine", "value": "ramen", **({"importance": cuisine} if cuisine else {})},
                       {"question_id": "vibe", "value": "quiet", **({"importance": vibe} if vibe else {})}]}

    def test_how_much_it_matters_tilts_a_members_own_balance(self):
        questions = [soft("cuisine", "cuisine"), soft("vibe", "vibe")]
        tied = execute(*snapshots(questions, self.answers()))
        self.assertEqual(tied["result"]["ranked_candidates"][0]["primary_objective_tie_size"], 2)
        self.assertEqual(winner(execute(*snapshots(questions, self.answers(cuisine="high")))), "a")
        self.assertEqual(winner(execute(*snapshots(questions, self.answers(vibe="high")))), "b")
        self.assertEqual(winner(execute(*snapshots(questions, self.answers(cuisine="low")))), "b")

    def test_unknown_levels_are_rejected(self):
        plan, replies = snapshots([soft("cuisine", "cuisine"), soft("vibe", "vibe")], self.answers(cuisine="extreme"))
        with self.assertRaises(SnapshotError):
            execute(plan, replies)


class FakeSimilarityProvider:
    model = "fake-similarity"

    def __init__(self, scores):
        self.scores, self.calls = scores, 0

    def canonicalize_sparse_label(self, payload):
        return {"status": "distinct", "target": None, "reason": "Different label"}

    def assess_similarity(self, payload):
        self.calls += 1
        return {"scores": [{"index": pair["index"], "score": self.scores.get((pair["preferred"], pair["actual"]), 0)}
                           for pair in payload["pairs"]]}


class SimilarityTests(unittest.TestCase):
    def test_model_judged_meaning_gives_partial_credit_and_is_frozen(self):
        questions = [soft("cuisine", "cuisine")]
        answers = {"m1": [{"question_id": "cuisine", "value": "japanese"}]}
        provider = FakeSimilarityProvider({("japanese", "ramen"): 1.0, ("japanese", "italian"): 0.0})
        run = execute(*snapshots(questions, answers), semantic_provider=provider)
        self.assertEqual(run["status"], "ranked", run.get("issues"))
        self.assertEqual(winner(run), "a")
        self.assertEqual(run["result"]["ranked_candidates"][0]["min_member_score"], 1.0)
        evidence = run["processing"]["semantic_evidence"]["similarity_assessments"]["cuisine"]
        self.assertIn({"preferred": "japanese", "actual": "ramen", "score": 1.0}, evidence)
        self.assertEqual(provider.calls, 1)

    def test_word_matching_still_applies_without_a_model(self):
        questions = [soft("cuisine", "cuisine")]
        answers = {"m1": [{"question_id": "cuisine", "value": "japanese"}]}
        run = execute(*snapshots(questions, answers))
        self.assertEqual(run["result"]["ranked_candidates"][0]["primary_objective_tie_size"], 2)

    def test_out_of_range_or_unasked_scores_are_dropped(self):
        from decision_service.preprocessing.similarity import validate_similarity
        pairs = [{"preferred": "japanese", "actual": "ramen"}]
        rows = validate_similarity({"scores": [{"index": 0, "score": 7}, {"index": 4, "score": 1}, {"index": 0, "score": True}]}, pairs)
        self.assertEqual(rows, [{"preferred": "japanese", "actual": "ramen", "score": 1.0}])


class EarlyCloseTests(unittest.TestCase):
    def test_members_left_out_by_an_early_close_do_not_block_or_count(self):
        questions = [soft("cuisine", "cuisine")]
        answers = {"m1": [{"question_id": "cuisine", "value": "ramen"}], "m2": []}
        plan, replies = snapshots(questions, answers, statuses={"m2": "incomplete"})
        run = execute(plan, replies)
        self.assertEqual(run["status"], "ranked", run.get("issues"))
        self.assertEqual(winner(run), "a")
        self.assertEqual(run["member_states"], {"m1": "complete", "m2": "not_counted"})
        self.assertEqual(recommendation_view(run)["not_counted_members"], 1)

    def test_required_incomplete_members_still_block(self):
        questions = [soft("cuisine", "cuisine")]
        plan, replies = snapshots(questions, {"m1": [{"question_id": "cuisine", "value": "ramen"}], "m2": []})
        replies = deepcopy(replies)
        replies["participants"][1]["response_status"] = "incomplete"
        self.assertEqual(execute(plan, replies)["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
