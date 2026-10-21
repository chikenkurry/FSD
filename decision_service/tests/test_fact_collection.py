from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import MagicMock, patch

from decision_service.service.fact_collection import (
    CollectionUnavailable, GeminiFactCollector, public_collection_input, validate_claims,
)
from decision_service.service.snapshots import SnapshotError


class GeminiCollectionTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"plan_id": "plan", "round_id": "round", "option_revision": 1, "option_snapshot_id": "snapshot",
                     "currency": "SGD", "cost_scope": "per_person_total", "roster": ["PRIVATE-MEMBER"],
                     "questions": [{"label": "PRIVATE-BUDGET"}],
                     "context": {"private": "PRIVATE-NOTE"},
                     "options": [{"option_id": "device-a", "title": "Device A",
                                  "identity": {"model_id": "ExactModel123", "variant": "16GB", "region": "SG"}}]}
        self.requests = [{"option_id": "device-a", "attribute_id": "mass", "value_type": "number", "unit": "kg"}]
        self.safe = public_collection_input(self.plan, self.requests)
        self.text = "ExactModel123 mass is 1.2 kg."
        self.metadata = {"webSearchQueries": ["ExactModel123 mass"],
                         "groundingChunks": [{"web": {"uri": "https://manufacturer.example/spec", "title": "Official specification"}}],
                         "groundingSupports": [{"segment": {"text": self.text}, "groundingChunkIndices": [0]}],
                         "searchEntryPoint": {"renderedContent": "<div>Search suggestions fixture</div>"}}
        self.claim = {"option_id": "device-a", "attribute_id": "mass", "entity_id": "ExactModel123",
                      "value_type": "number", "value": 1.2, "unit": "kg", "qualifier": "exact",
                      "source_text": self.text, "valid_until": None}

    def test_search_projection_excludes_members_answers_and_free_form_context(self):
        projected = json.dumps(self.safe)
        self.assertNotIn("PRIVATE", projected)
        self.assertEqual(set(self.safe), {"options", "requests", "currency", "cost_scope"})

    def test_ambiguous_identity_and_unknown_request_are_rejected_before_network(self):
        for change in ("identity", "option", "type"):
            plan, requests = deepcopy(self.plan), deepcopy(self.requests)
            if change == "identity":
                del plan["options"][0]["identity"]
            elif change == "option":
                requests[0]["option_id"] = "other-plan-option"
            else:
                requests[0]["value_type"] = "imagined"
            with self.subTest(change=change), self.assertRaises(SnapshotError):
                public_collection_input(plan, requests)

    def test_search_citations_produce_pending_claims_with_provider_sources(self):
        claims, issues = validate_claims([self.claim], self.safe, self.text, self.metadata)
        self.assertFalse(issues)
        self.assertEqual(claims[0]["review_state"], "pending")
        self.assertEqual(claims[0]["fact_status"], "estimated")
        self.assertEqual(claims[0]["identity"],self.plan["options"][0]["identity"])
        self.assertEqual(claims[0]["sources"][0]["url"], "https://manufacturer.example/spec")

    def test_citation_on_an_overlapping_segment_that_states_the_value_is_accepted(self):
        text = "### Bistro\n**Cuisine**: Modern French (as described by the restaurant)"
        metadata = deepcopy(self.metadata)
        metadata["groundingSupports"] = [{"segment": {"text": "**Cuisine**: Modern French"}, "groundingChunkIndices": [0]}]
        safe = public_collection_input({**self.plan, "options": [{**self.plan["options"][0]}]},
                                       [{"option_id": "device-a", "attribute_id": "cuisine", "value_type": "category", "unit": None}])
        claim = {**self.claim, "attribute_id": "cuisine", "value_type": "category", "value": "Modern French", "unit": None,
                 "source_text": "Modern French (as described by the restaurant)"}
        claims, issues = validate_claims([claim], safe, text, metadata)
        self.assertFalse(issues)
        self.assertEqual(claims[0]["sources"][0]["url"], "https://manufacturer.example/spec")
        # An overlapping citation that states a different value does not support the claim.
        claims, issues = validate_claims([{**claim, "value": "Japanese", "source_text": "Modern French (as described by the restaurant)"}], safe, text, metadata)
        self.assertFalse(claims)

    def test_uncited_values_and_invented_source_phrases_are_not_accepted(self):
        for change in ("citation", "excerpt", "identity", "unit", "type", "missing"):
            claim, metadata = deepcopy(self.claim), deepcopy(self.metadata)
            if change == "citation":
                metadata["groundingSupports"] = []
            elif change == "excerpt":
                claim["source_text"] = "invented 1.2 kg"
            elif change == "identity":
                claim["entity_id"] = "OtherModel"
            elif change == "unit":
                claim["unit"] = "lbs"
            elif change == "type":
                claim["value"] = True
            else:
                del claim["valid_until"]
            with self.subTest(change=change):
                claims, issues = validate_claims([claim], self.safe, self.text, metadata)
                self.assertFalse(claims)
                self.assertTrue(issues)

    def test_qualifiers_and_conflicts_are_preserved_for_review(self):
        qualified = {**self.claim, "qualifier": "up_to"}
        other = "Another source states ExactModel123 mass is 1.3 kg."
        conflict = {**self.claim, "value": 1.3, "source_text": other}
        metadata = deepcopy(self.metadata)
        metadata["groundingSupports"].append({"segment": {"text": other}, "groundingChunkIndices": [0]})
        claims, _ = validate_claims([qualified, conflict], self.safe, self.text + " " + other, metadata)
        self.assertEqual(len(claims), 2)
        self.assertEqual(claims[0]["qualifier"], "up_to")
        self.assertTrue(all(c["review_state"] == "pending" for c in claims))

    def test_expired_offers_are_excluded(self):
        expired = {**self.claim, "valid_until": (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()}
        claims, issues = validate_claims([expired], self.safe, self.text, self.metadata)
        self.assertFalse(claims)
        self.assertEqual(issues[0]["code"], "EXPIRED_OR_INVALID_FACT")

    def test_private_or_unsecured_citation_urls_are_excluded(self):
        for uri in ("http://manufacturer.example", "https://127.0.0.1", "https://localhost/path", "https://host.internal/path"):
            metadata = deepcopy(self.metadata)
            metadata["groundingChunks"][0]["web"]["uri"] = uri
            with self.subTest(uri=uri):
                self.assertFalse(validate_claims([self.claim], self.safe, self.text, metadata)[0])

    def test_transport_uses_search_metadata_then_json_extraction_and_keeps_search_widget(self):
        collector = GeminiFactCollector(api_key="fixture-key", model="fixture-model")
        grounded = {"finishReason": "STOP", "content": {"parts": [{"text": self.text}]}, "groundingMetadata": self.metadata}
        extracted = {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps({"claims": [self.claim]})}]}}
        replies = []
        for candidate in (grounded, extracted):
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({"candidates": [candidate]}).encode()
            replies.append(response)
        with patch("decision_service.service.fact_collection.urlopen", side_effect=replies) as transport:
            result = collector.collect(self.safe)
        first = json.loads(transport.call_args_list[0].args[0].data)
        second = json.loads(transport.call_args_list[1].args[0].data)
        self.assertEqual(first["tools"], [{"google_search": {}}])
        self.assertNotIn("tools", second)
        self.assertIn("responseJsonSchema", second["generationConfig"])
        self.assertEqual(result["claims"][0]["value"], 1.2)
        self.assertIn("searchEntryPoint", result["grounding"])
        self.assertNotIn("PRIVATE", json.dumps(first))

    def test_provider_search_omission_does_not_become_confirmed_evidence(self):
        collector = GeminiFactCollector(api_key="fixture-key", model="fixture-model")
        with patch.object(collector, "request", return_value={"content": {"parts": [{"text": self.text}]}}) as request:
            result = collector.collect(self.safe)
        self.assertFalse(result["claims"])
        self.assertEqual(result["issues"][0]["code"], "SEARCH_EVIDENCE_REQUIRED")
        self.assertEqual(request.call_count, 1)
