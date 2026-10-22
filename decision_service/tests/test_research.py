import json
import unittest
from unittest.mock import MagicMock

from decision_service.service.places import is_region, overview
from decision_service.service.research import Researcher
from decision_service.service.snapshots import SnapshotError


def reply(payload):
    return {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.gemini = MagicMock()
        self.places = MagicMock()
        self.body = {"decision_question": "Where should we eat?", "category": "Event", "region": "Singapore", "currency": "SGD",
                     "options": [{"key": "a", "title": "Odette"}, {"key": "b", "title": "Japan"}, {"key": "c", "title": "Cycling"}]}

    def test_places_resolve_venues_and_resort_regions_as_destinations(self):
        researcher = Researcher(self.gemini, self.places)
        self.gemini.request.side_effect = lambda prompt, **kw: reply({"options": [
            {"key": "a", "kind": "place"}, {"key": "b", "kind": "place"}, {"key": "c", "kind": "activity"}]}) if "Classify" in prompt else (
            reply({"summary": "A general summary."}) if "schema" in kw else {"content": {"parts": [{"text": "Search text."}]}, "groundingMetadata": {}})
        self.places.find.side_effect = lambda title, region: {"id": "venue-place-id", "types": ["restaurant"]} if title == "Odette" else {"id": "country-place-id", "types": ["country"]}
        self.places.details.side_effect = lambda pid: {"id": pid, "displayName": {"text": "Odette"}, "rating": 4.7, "userRatingCount": 900,
                                                       "photos": [{"name": f"places/{pid}/photos/photo-reference-1", "authorAttributions": [{"displayName": "A"}]}]}
        result = {row["key"]: row for row in researcher.overviews(self.body)["options"]}
        self.assertEqual(result["a"]["kind"], "place")
        self.assertEqual(result["a"]["overview"]["source"], "google_places")
        self.assertEqual(result["a"]["overview"]["rating"], 4.7)
        # Venues combine Places details with a web summary and highlights.
        self.assertEqual(result["a"]["overview"]["summary"], "A general summary.")
        self.assertEqual(result["b"]["kind"], "destination")
        self.assertEqual(result["b"]["overview"]["photos"][0]["attributions"][0]["name"], "A")
        self.assertEqual(result["c"]["overview"]["source"], "ai_general")
        self.places.find.assert_any_call("Odette", region="Singapore")

    def test_without_places_every_option_still_gets_a_web_or_general_overview(self):
        researcher = Researcher(self.gemini, None)
        self.gemini.request.side_effect = lambda prompt, **kw: reply({"options": [{"key": "a", "kind": "place"}]}) if "Classify" in prompt else (
            reply({"summary": "Modern French fine dining."}) if "schema" in kw else {"content": {"parts": [{"text": "Odette serves French."}]}, "groundingMetadata": {}})
        result = researcher.overviews({**self.body, "options": [self.body["options"][0]]})["options"][0]
        self.assertEqual(result["overview"]["source"], "web_search")
        self.assertEqual(result["overview"]["photos"], [])

    def test_drafted_questions_need_choices_and_budget_becomes_a_cost_requirement(self):
        self.gemini.request.return_value = reply({"questions": [
            {"title": "What mood are you after?", "type": "single", "role": "preference", "criterion": "Atmosphere", "choices": ["Cosy", "Lively"]},
            {"title": "Budget?", "type": "budget", "role": "preference", "criterion": "spend", "choices": []},
            {"title": "One choice only", "type": "single", "role": "preference", "criterion": "solo", "choices": ["Only"]}]})
        drafted = Researcher(self.gemini, None).draft_questions({**self.body, "options": [{"title": "Odette", "summary": ""}]})["questions"]
        self.assertEqual([q["criterion"] for q in drafted], ["atmosphere", "max_cost"])
        self.assertEqual(drafted[1]["role"], "requirement")

    def test_fit_keeps_only_the_questions_own_choices(self):
        self.gemini.request.side_effect = [
            {"content": {"parts": [{"text": "Odette is intimate and romantic."}]}, "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://example.com/review", "title": "Review"}}]}},
            reply({"facts": [{"option": "a", "criterion": "atmosphere", "values": ["Romantic", "Invented"], "known": True, "reason": "Reviews call it intimate."},
                             {"option": "b", "criterion": "atmosphere", "values": ["Lively"], "known": False, "reason": "Unclear."}]})]
        body = {**self.body, "questions": [{"criterion": "atmosphere", "title": "Mood?", "type": "single", "choices": ["Romantic", "Lively"]}]}
        facts = Researcher(self.gemini, None).fit(body)["facts"]
        self.assertEqual(facts, [{"option": "a", "criterion": "atmosphere", "values": ["Romantic"], "reason": "Reviews call it intimate.",
                                  "sources": [{"url": "https://example.com/review", "title": "Review"}]}])

    def test_grounded_extraction_preserves_option_keys_and_exact_question_choices(self):
        self.gemini.request.side_effect = [
            {"content": {"parts": [{"text": "Odette offers an intimate setting."}]}, "groundingMetadata": {}},
            reply({"facts": [{"option": "a", "criterion": "atmosphere", "values": ["Quiet and intimate"],
                              "known": True, "reason": "The search describes an intimate setting."}]})]
        body = {**self.body, "questions": [{"criterion": "atmosphere", "title": "What atmosphere?", "type": "single",
                                           "choices": ["Quiet and intimate", "Lively and social"]}]}
        result = Researcher(self.gemini, None).fit(body)
        extraction = self.gemini.request.call_args_list[1].args[0]
        self.assertIn('"key": "a", "title": "Odette"', extraction)
        self.assertIn('"criterion": "atmosphere"', extraction)
        self.assertIn('"Quiet and intimate"', extraction)
        self.assertIn('never as factual evidence', extraction)
        self.assertIn('set known=false when unsupported', extraction)
        self.assertEqual(result["facts"][0]["values"], ["Quiet and intimate"])

    def test_budget_fit_returns_one_positive_amount(self):
        self.gemini.request.side_effect = [
            {"content": {"parts": [{"text": "A tasting menu costs about SGD 498."}]}, "groundingMetadata": {}},
            reply({"facts": [{"option": "a", "criterion": "max_cost", "values": ["SGD 498"], "known": True, "reason": "Menu price."},
                             {"option": "b", "criterion": "max_cost", "values": ["-5"], "known": True, "reason": "Invalid."}]})]
        body = {**self.body, "questions": [{"criterion": "max_cost", "title": "Budget?", "type": "budget", "choices": []}]}
        facts = Researcher(self.gemini, None).fit(body)["facts"]
        self.assertEqual([(f["option"], f["values"]) for f in facts], [("a", ["498"])])

    def test_research_corrections_and_source_urls_are_context_to_verify(self):
        self.gemini.request.side_effect = [
            {"content": {"parts": [{"text": "The current menu states SGD 85."}]}, "groundingMetadata": {}},
            reply({"facts": [{"option": "a", "criterion": "max_cost", "values": ["85"], "known": True, "reason": "Current menu."}]})]
        body = {**self.body, "options": [{"key":"a","title":"Venue","source_url":"https://example.com/menu"}],
                "correction":"Check the current menu instead of last year's price.",
                "questions":[{"criterion":"max_cost","title":"Budget?","type":"budget","choices":[]}]}
        facts = Researcher(self.gemini,None).fit(body)["facts"]
        query = self.gemini.request.call_args_list[0].args[0]
        self.assertIn("https://example.com/menu",query)
        self.assertIn(body["correction"],query)
        self.assertIn("never as factual evidence",self.gemini.request.call_args_list[1].args[0])
        self.assertEqual(facts[0]["values"],["85"])

    def test_summaries_keep_two_whole_sentences(self):
        from decision_service.service.research import sentences
        self.assertEqual(sentences("One. Two is here. Three is long.", 2, 320), "One. Two is here.")
        self.assertTrue(sentences("word " * 200, 2, 50).endswith("…"))

    def test_research_worker_starts_without_a_gemini_key(self):
        # CI runs the stack without provider keys; the worker must still start.
        import os
        from unittest.mock import patch
        from decision_service.service import __main__ as entry
        started = {}
        class Stop(Exception):
            pass
        def fake_server(*args, **kwargs):
            started["kinds"] = list(kwargs["jobs"].specifications)
            started["researcher"] = kwargs["jobs"].researcher
            raise Stop()
        environment = {"INTERNAL_API_TOKEN": "x" * 16, "SEMANTIC_PROVIDER": "rules"}
        with patch.dict(os.environ, environment, clear=True), patch.object(entry, "open_store", return_value=MagicMock()), \
                patch.object(entry, "DecisionServer", side_effect=fake_server), \
                patch("sys.argv", ["decision", "--role", "worker", "--kinds", "research"]), self.assertRaises(Stop):
            entry.main()
        self.assertEqual(started["kinds"], ["research"])
        self.assertIsNone(started["researcher"].gemini)

    def test_inputs_are_validated_before_any_provider_call(self):
        with self.assertRaises(SnapshotError):
            Researcher(self.gemini, self.places).overviews({"options": [{"key": "a", "title": ""}]})
        self.gemini.request.assert_not_called()

    def test_place_overview_is_display_only_and_keeps_photo_credits(self):
        card = overview({"id": "abc", "displayName": {"text": "Park"}, "types": ["park"], "priceLevel": "PRICE_LEVEL_MODERATE",
                         "photos": [{"name": "places/abcdefghijk/photos/reference-value", "authorAttributions": [{"displayName": "B", "uri": "https://maps.google.com/x"}]},
                                    {"name": "not-a-photo"}]})
        self.assertEqual(card["price_level"], 2)
        self.assertEqual(len(card["photos"]), 1)
        self.assertFalse(is_region({"types": ["restaurant"]}))
        self.assertTrue(is_region({"types": ["country", "political"]}))


if __name__ == "__main__":
    unittest.main()
