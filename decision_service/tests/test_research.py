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

    def test_drafted_questions_carry_a_suggested_weight_defaulting_to_normal(self):
        self.gemini.request.return_value = reply({"questions": [
            {"title": "Which cuisine?", "type": "written", "role": "preference", "criterion": "cuisine", "choices": [], "weight": "more"},
            {"title": "Indoors?", "type": "yes_no", "role": "preference", "criterion": "indoor", "choices": [], "weight": "huge"},
            {"title": "Music?", "type": "written", "role": "preference", "criterion": "music", "choices": []}]})
        drafted = Researcher(self.gemini, None).draft_questions({**self.body, "options": [{"title": "Odette", "summary": ""}]})["questions"]
        self.assertEqual([q["weight"] for q in drafted], ["more", "normal", "normal"])

    def test_facts_collect_neutral_values_without_question_choices_or_private_context(self):
        self.gemini.collect.return_value = {"claims": [{"claim_id":"claim-a","option_id":"a","attribute_id":"atmosphere",
            "value_type":"category","value":"intimate","unit":None,"qualifier":"exact","source_text":"Odette is intimate.",
            "valid_until":None,"sources":[{"url":"https://example.com/review"}]}], "issues":[],"retrieved_at":"2026-10-22T00:00:00Z"}
        body = {**self.body,"options":[self.body["options"][0]],"attributes":[{"criterion":"atmosphere","value_type":"category"}],
                "questions":[{"title":"Private question","choices":["Quiet","Lively"]}], "summaries":{"a":"Unverified claim"},
                "member_answers":"Private answer", "decision_question":"Private goal"}
        result = Researcher(self.gemini,None).facts(body)
        inputs = self.gemini.collect.call_args.args[0]
        self.assertEqual(inputs["requests"],[{"option_id":"a","attribute_id":"atmosphere","value_type":"category","unit":None}])
        for excluded in ('Private question','Quiet','Private answer','Private goal','Unverified claim'):
            self.assertNotIn(excluded,json.dumps(inputs))
        self.assertEqual(result["facts"][0]["value"],"intimate")
        self.assertEqual(result["facts"][0]["context"]["source_text"],"Odette is intimate.")
        # Changing choices must have no effect on the public facts request.
        body["questions"][0]["choices"]=["Peaceful","Busy"]
        Researcher(self.gemini,None).facts(body)
        self.assertEqual(self.gemini.collect.call_args.args[0],inputs)

    def test_fact_corrections_are_bounded_context_to_verify(self):
        self.gemini.collect.return_value={"claims":[],"issues":[{"code":"SEARCH_EVIDENCE_REQUIRED"}]}
        body={**self.body,"options":[{"key":"a","title":"Venue","source_url":"https://example.com/menu"}],
              "attributes":[{"criterion":"max_cost","value_type":"decimal","unit":"SGD"}],
              "correction":"Check the current menu instead of last year's price."}
        self.assertEqual(Researcher(self.gemini,None).facts(body)["facts"],[])
        inputs=self.gemini.collect.call_args.args[0]
        self.assertEqual(inputs["options"][0]["identity"]["source_url"],"https://example.com/menu")
        self.assertEqual(inputs["organiser_correction_to_verify"],body["correction"])
        with self.assertRaises(SnapshotError):
            Researcher(self.gemini,None).facts({**body,"correction":"x"*1001})

    def test_fact_types_and_duplicate_attributes_are_rejected_before_collection(self):
        for attributes in ([{"criterion":"cost","value_type":"guess"}],
                           [{"criterion":"max_cost","value_type":"decimal","unit":"USD"}],
                           [{"criterion":"atmosphere","value_type":"category"}]*2):
            with self.subTest(attributes=attributes),self.assertRaises(SnapshotError):
                Researcher(self.gemini,None).facts({**self.body,"attributes":attributes})
        self.gemini.collect.assert_not_called()

    def test_written_questions_declare_option_fact_type_without_assigning_choices(self):
        self.gemini.request.return_value=reply({"questions":[{"title":"What setting do you prefer?","type":"written","role":"preference",
                                                            "criterion":"atmosphere","value_type":"tag_set","choices":[]}]})
        drafted=Researcher(self.gemini,None).draft_questions({**self.body,"options":[{"title":"Venue","summary":"A quiet terrace."}]})["questions"]
        self.assertEqual(drafted[0]["type"],"written")
        self.assertEqual(drafted[0]["value_type"],"tag_set")
        self.assertEqual(drafted[0]["choices"],[])

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
