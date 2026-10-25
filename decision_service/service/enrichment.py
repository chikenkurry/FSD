"""Supplement missing option attributes without sending member data to Gemini.

The original published snapshot stays immutable. Adopted evidence is recorded in
the run so that the exact factual input to the algorithm can be replayed offline.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
import threading
import time

from .fact_collection import CollectionUnavailable, public_collection_input, valid_value
from .snapshots import SnapshotError
from .store import canonical
from decision_service.preprocessing.generic_mapping import infer_type

POLICY = "grounded-option-facts-v1"
FRESH_SECONDS = 6 * 60 * 60


def specification():
    model = os.environ.get("GEMINI_FACT_MODEL", "gemini-3.8-flash")
    return {"policy": POLICY, "model": model,
            "model_revision": os.environ.get("GEMINI_FACT_MODEL_REVISION") or model}


def unexpired(value):
    if value is None:
        return True
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.tzinfo is not None and stamp > datetime.now(timezone.utc)
    except (ValueError, AttributeError):
        return False


def requested_facts(planning, responses):
    """Typed public attributes only; question text and answer values stay local."""
    definitions = {}
    active = {q.get("criterion") for q in planning["questions"] if q.get("role") in {"soft", "hard"}}
    for option in planning["options"]:
        for fact in option.get("facts", []):
            if fact.get("value_type") and (fact["criterion"] in active or "preferences" in active):
                definitions[fact["criterion"]] = (fact["value_type"], fact.get("unit"))
    for question in planning["questions"]:
        mapping = question.get("mapping", {})
        if question.get("role") in {"soft", "hard"} and mapping.get("value_type"):
            definitions[question["criterion"]] = (mapping["value_type"], mapping.get("unit"))
    if any(row.get("budget", {}).get("kind") == "limited" for row in responses.get("constraints", [])):
        definitions["max_cost"] = ("decimal", planning["currency"])
    requests = []
    for option in planning["options"]:
        known = {f["criterion"]: f for f in option.get("facts", [])}
        for attribute, (kind, unit) in sorted(definitions.items()):
            fact = known.get(attribute)
            if (fact and fact.get("status") == "confirmed" and not fact.get("context", {}).get("stale")
                    and unexpired(fact.get("context", {}).get("valid_until"))):
                continue
            requests.append({"option_id": option["option_id"], "attribute_id": attribute,
                             "value_type": kind, "unit": unit})
    return requests


class FactEnricher:
    def __init__(self, collector=None, store=None):
        self.collector, self.store = collector, store
        self.locks = [threading.Lock() for _ in range(32)]

    def collection(self, inputs):
        if self.collector is None:
            raise CollectionUnavailable("FACT_COLLECTOR_NOT_CONFIGURED", retryable=False)
        # A shared six-hour bucket reuses public research between member previews
        # and recommendations. Provider/model revisions and identity fence reuse.
        key = hashlib.sha256(canonical({"enrichment": specification(), "inputs": inputs,
            "freshness_bucket": int(time.time() // FRESH_SECONDS)}).encode()).hexdigest()
        if self.store is None:
            return self.collector.collect(inputs)
        with self.locks[int(key[:8], 16) % len(self.locks)]:
            return deepcopy(self.store.cache_get_or_produce(key, lambda: self.collector.collect(inputs)))

    def enrich(self, planning, responses, *, extra_requests=None):
        enriched = deepcopy(planning)
        audit = {"policy": POLICY, "applied_facts": [], "invalidated_facts": [], "collections": [], "issues": []}
        # Legacy rounds and date-scoped scenario costs retain their own policy.
        if planning.get("interpretation_policy") != "facts-v1" or planning.get("execution_mode", "options") != "options":
            return enriched, audit
        requests = list(extra_requests) if extra_requests is not None else requested_facts(planning, responses)
        # If a previously confirmed fact expired or its option identity changed,
        # an unsuccessful refresh must leave an unknown, never a usable old value.
        for option in enriched["options"]:
            for fact in option.get("facts", []):
                context = fact.get("context", {})
                if context.get("stale") or not unexpired(context.get("valid_until")):
                    kind = fact.get("value_type") or ("decimal" if fact["criterion"] == "max_cost" else
                                                      infer_type(fact["value"], "planning.options.facts"))
                    fact.update(status="unknown", value=None, value_type=kind)
                    audit["invalidated_facts"].append({"option_id": option["option_id"], "fact": deepcopy(fact)})
        if not requests:
            return enriched, audit
        # A missing/ambiguous identity must not poison the other options' lookup.
        eligible = []
        for request in requests:
            try:
                public_collection_input(planning, [request])
                eligible.append(request)
            except SnapshotError:
                audit["issues"].append({"code": "FACT_IDENTITY_OR_TYPE_REQUIRED", "option_id": request["option_id"],
                                        "attribute_id": request["attribute_id"]})
        if not eligible:
            promote_estimated_facts(enriched, requests, audit)
            return enriched, audit
        if len(eligible) > 64:
            audit["issues"].append({"code": "FACT_ENRICHMENT_LIMIT"})
            promote_estimated_facts(enriched, requests, audit)
            return enriched, audit
        inputs = public_collection_input(planning, eligible)
        try:
            collection = self.collection(inputs)
        except CollectionUnavailable as error:
            audit["issues"].append({"code": error.code})
            promote_estimated_facts(enriched, requests, audit)
            return enriched, audit
        audit["collections"].append(collection)
        audit["issues"].extend(collection.get("issues", []))
        apply_collection(enriched, eligible, collection, audit)
        promote_estimated_facts(enriched, requests, audit)
        return enriched, audit


def promote_estimated_facts(planning, requests, audit):
    """Promote existing non-stale, non-conditional estimated facts when no replacement was applied."""
    options = {o["option_id"]: o for o in planning["options"]}
    applied = {(row["option_id"], row["fact"]["criterion"]) for row in audit.get("applied_facts", [])}
    for request in requests:
        if (request["option_id"], request["attribute_id"]) in applied:
            continue
        option = options.get(request["option_id"])
        if not option:
            continue
        for fact in option.get("facts", []):
            if fact.get("criterion") != request["attribute_id"] or fact.get("status") != "estimated":
                continue
            context = fact.get("context") or {}
            if (context.get("stale") or not unexpired(context.get("valid_until"))
                    or context.get("qualifier") == "conditions" or context.get("alternatives")
                    or not valid_value(fact.get("value"), request["value_type"])):
                continue
            fact["status"] = "confirmed"
            audit["applied_facts"].append({"option_id": option["option_id"], "fact": deepcopy(fact)})
            applied.add((request["option_id"], request["attribute_id"]))


def apply_collection(planning, requests, collection, audit):
    """Only a unique, non-conditional, current, cited finding is eligible for comparison."""
    options = {o["option_id"]: o for o in planning["options"]}
    for request in requests:
        matches = [c for c in collection.get("claims", []) if
                   (c.get("option_id"), c.get("attribute_id"), c.get("value_type"), c.get("unit")) ==
                   (request["option_id"], request["attribute_id"], request["value_type"], request["unit"])]
        # Include conditional/expired findings in conflict detection; never pick
        # a favourable claim merely because the others are ineligible.
        eligible = [c for c in matches if c.get("qualifier") and c.get("qualifier") != "conditions"
                    and c.get("sources") and c.get("source_text") and unexpired(c.get("valid_until"))
                    and valid_value(c.get("value"), request["value_type"])]
        if request["value_type"] == "tag_set":
            if not eligible or len(eligible) != len(matches):
                continue
            claim = deepcopy(eligible[0])
            claim["value"] = list(dict.fromkeys(tag for c in eligible for tag in c["value"]))
            claim["sources"] = list({s["url"]: s for c in eligible for s in c["sources"]}.values())
        else:
            values = {canonical(c.get("value")) for c in matches}
            if len(values) != 1 or not eligible:
                continue
            claim = eligible[0]
        option = options[request["option_id"]]
        context = {"verification": "grounded_search", "reviewed": False, "claim_id": claim.get("claim_id"),
                   "source_text": claim["source_text"], "sources": claim["sources"],
                   "qualifier": claim.get("qualifier") or "exact", "retrieved_at": collection.get("retrieved_at"),
                   "valid_until": claim.get("valid_until"), "enrichment_policy": POLICY}
        if request["attribute_id"] == "max_cost":
            context["scope"] = planning["cost_scope"]
        fact = {"criterion": request["attribute_id"], "value": claim["value"],
                "value_type": request["value_type"], "status": "confirmed",
                "source": claim["sources"][0]["url"], "context": context}
        if request["unit"]:
            fact["unit"] = request["unit"]
        option["facts"] = [f for f in option.get("facts", []) if f["criterion"] != request["attribute_id"]] + [fact]
        audit["applied_facts"].append({"option_id": option["option_id"], "fact": deepcopy(fact)})


def replay_facts(planning, audit):
    """Rebuild the executed snapshot using persisted facts, without web access."""
    replay = deepcopy(planning)
    options = {o["option_id"]: o for o in replay["options"]}
    for row in audit.get("invalidated_facts", []) + audit.get("applied_facts", []):
        option, fact = options[row["option_id"]], deepcopy(row["fact"])
        option["facts"] = [f for f in option.get("facts", []) if f["criterion"] != fact["criterion"]] + [fact]
    return replay
