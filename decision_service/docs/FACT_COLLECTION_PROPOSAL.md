# Fact collection proposal

Research date: 8 October 2026. No collector, network client, source connector,
scraper, or automated approval was implemented for this proposal.

## What would become automated

`fact_registry()` already derives criterion types and units from supplied option
facts and `planning.criteria`. It is a schema registry, not a source of external
information. The missing component is acquisition: finding evidence for an
option and producing the fact records the registry can validate.

Keep acquisition outside `preprocess()`. Preprocessing should remain a function
of frozen snapshots, policy and saved semantic evidence. A separate collector
can consume `preparation.fact_requests` and `scenario_requests`, retrieve claims,
then publish a new planning snapshot with a new revision/snapshot ID. Re-run
preprocessing against that snapshot. Existing rounds should retain the facts
they actually used, even if prices or specifications later change.

## Using an LLM with web search

A search-enabled LLM is a practical proposed collector: it can discover sources
across domains and extract the requested fields without a custom connector for
every website. Keep the existing registry responsible for types and units, and
give the collector responsibility for finding candidate claims with evidence.

For example, Gemini's Google Search grounding exposes executed search queries
and citation annotations. The model decides whether to search, so enabling the
tool alone does not establish that a particular answer used retrieved evidence.
Search can also be combined with its URL context tool for specific pages.
[Google Search grounding](https://ai.google.dev/gemini-api/docs/google-search).
Claude also offers a hosted web search tool.
[Claude web search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool).
These are possible providers, not integrations tested in this project.

The proposed path is:

```text
Missing fact requests + option identity + necessary scenario context
  -> LLM searches and reads relevant sources
  -> candidate claims with values, qualifiers and source evidence
  -> code validates identity, types, units, support and freshness
  -> accepted facts in a new frozen planning snapshot
  -> preprocessing runs again
```

Use citation metadata returned by the search tool, not just URLs written in the
model's answer. Require evidence of retrieval for each claim. If the provider
does not expose enough source content to check an excerpt, fetch the cited page
through a separate retrieval tool. A search snippet or citation alone does not
prove that the source supports the value, variant or interpretation.

For example, a request for a particular laptop's battery life might find an
official specification saying “up to 12 hours.” The candidate must preserve
`value: 12`, `unit: hours`, the `up_to` qualifier, exact model/variant and supporting
excerpt. It can support an advertised maximum criterion; it cannot establish a
12-hour actual-use minimum. If the requested measurement is absent, return an
unresolved request rather than substitute the advertised value.

Objective extracted claims can be accepted automatically when explicit evidence
and validation rules pass. Ambiguous identity, unsupported excerpts, conflicting
sources or unsuitable measurement conditions remain estimated or unresolved.
Search-assisted generation does not itself justify `status: confirmed`.

This collector would be separate from the local model that interprets member
answers. Send only the option identity, requested criteria and necessary scenario
context to search. Keep retrieval outside preprocessing so decisions can be
replayed against the same saved facts.

## Source choices

| Source | Useful for | Main limitation |
| --- | --- | --- |
| Official manufacturer, venue or supplier API/feed | Product specifications, declared facilities, current quotations | Different providers expose different attributes; access may require a commercial agreement. |
| Structured data on an official product page | Product identity, properties and offers | Coverage varies. Publisher markup is a claim, not independent verification. |
| Referenced public knowledge base | Stable entity identifiers and background attributes | A referenced statement still needs the right date, entity and underlying source. |
| Domain-specific commercial API | Date-sensitive prices and availability | Credentials, scope, access terms, coverage and expiration must be checked for the intended use. |
| Retrieved documents plus constrained extraction | Specifications or policies available only as prose/PDF | Qualifiers and contradictions require review; an extraction model must not fill gaps from memory. |

Schema.org `Product` includes identifiers and `additionalProperty`; `PropertyValue`
supports named values, units and bounds. `Offer` represents commercial offers,
including price/currency, and `priceValidUntil` describes price expiry. These
formats are worth inspecting before attempting prose extraction. They do not
guarantee that a publisher's data is correct. [Product](https://schema.org/Product),
[PropertyValue](https://schema.org/PropertyValue), [Offer](https://schema.org/Offer),
[priceValidUntil](https://schema.org/priceValidUntil).

GS1 can help establish product/company identity from supplied identifiers.
Its service offers foundational data, not a guarantee that every required
technical specification is present; advanced access depends on the service
arrangement. [Verified by GS1](https://www2.gs1.org/services/verified-by-gs1),
[GS1 access guidance](https://support.gs1.org/support/solutions/articles/43000734077-what-is-verified-by-gs1-).

Wikidata exposes entity access and query interfaces. Use it for identity and
appropriate referenced attributes, rather than treating it as a live price
service. Wikidata itself describes its statements as claims supported by other
sources. [Data access](https://www.wikidata.org/wiki/Wikidata:Data_access),
[Verifiability](https://www.wikidata.org/wiki/Wikidata:Verifiability).

For travel, Duffel documents offer requests parameterized by passengers and
journey slices, and offers with amounts, currencies and expiry. This is a
possible source adapter, not a tested integration or a complete trip-budget
solution. Hotel access also needs investigation: Booking.com's Demand API
requires managed affiliate access and credentials. [Duffel requests](https://duffel.com/docs/api/offer-requests),
[Duffel offers](https://duffel.com/docs/api/offers),
[Booking.com prerequisites](https://developers.booking.com/demand/docs/getting-started/prerequisites).

## Proposed collection flow

1. **Resolve the entity.** Start with an official URL, product/model identifier,
   provider ID or other stable identifier. Confirm the variant, region and seller.
   A display name such as “Device A” is insufficient. Ambiguous names return an
   identity question instead of attaching facts from a guessed entity.
2. **Choose the source.** Let the search-enabled collector discover relevant
   pages, preferring official sources. Use direct API fields or structured data
   when available, and read source pages instead of relying on search snippets.
   Retrieval should follow the source's access terms and crawler instructions;
   robots.txt describes crawler rules, not access authorization. [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html).
3. **Retrieve and retain evidence.** Store the URL/provider ID, retrieval time,
   raw payload or permitted excerpt, content hash and source revision when supplied.
   A useful provenance model distinguishes the source document, retrieval or
   extraction activity, and responsible publisher/extractor. [W3C PROV primer](https://www.w3.org/TR/prov-primer/).
4. **Extract a claim.** Deterministic adapters map declared fields. A model may
   extract from retrieved text, but every claim must point to an exact supporting
   field/excerpt. Return missing information for absent values. Do not execute
   instructions embedded in retrieved material.
5. **Validate meaning and context.** Check criterion, type, unit, qualifiers,
   variant, measurement method and applicability. “Up to 12 hours” supports an
   advertised maximum; it does not prove 12 hours of actual battery life. Currency
   conversion and unit conversion should be explicit, versioned operations.
6. **Resolve conflicts and freshness.** Retain competing claims; do not let the
   last fetched value win automatically. Apply source/criterion rules or ask for
   review. Expired offers and stale evidence return to collection. An API price
   valid for two travellers must not become a per-person total without an explicit
   calculation and evidence for what the quote includes.
7. **Publish accepted facts.** Map accepted claims to the existing input envelope,
   preserve their evidence, and freeze a new planning snapshot. Retrieval success
   or model confidence alone must not assign `status: confirmed`.

## Proposed evidence record

This is a design example, not a new supported input schema:

```json
{
  "claim_id": "claim-123",
  "option_id": "device-a",
  "entity": {"model_id": "supplier-model-id", "variant": "exact-variant"},
  "criterion": "advertised_battery_life",
  "value": 12,
  "value_type": "number",
  "unit": "hours",
  "qualifier": "up_to",
  "source_url": "https://supplier.example/specification",
  "source_field": "battery.maximumRuntime",
  "retrieved_at": "2026-10-08T00:00:00Z",
  "valid_until": null,
  "evidence_hash": "content-hash",
  "extractor_version": "adapter-version",
  "review_state": "pending"
}
```

The accepted projection would use `{criterion, value, value_type, unit, status,
source, context}` in `planning.options[].facts`. Evidence IDs and applicability
can live in `context`, while full evidence resides in a separate store. Current
preprocessing preserves that context but does not independently verify it; a
collector would need its own claim validator and acceptance policy.

## What should remain subject to review

Objective fields from an approved source can be accepted automatically under
explicit validation rules, including model-extracted fields with verifiable
support. Preserve qualifiers; if they do not satisfy the requested meaning,
leave that request unresolved. Stale, unsupported or conflicting claims should
remain estimated or unresolved. A member confirming a requirement
confirms what they meant; it does not confirm that an option satisfies it.

Qualitative suitability is harder to automate. “Good for coding,” “quiet,” or
“accessible” need operational definitions and evidence. Source marketing tags
and model suggestions should not become confirmed option facts merely because
their labels resemble member preferences.

## Recommended first increment

Start with product decisions and leader-supplied official URLs/model IDs. Use a
search-enabled LLM to find and extract a small number of objective criteria, such
as dimensions, mass and advertised specifications. Require a structured candidate
record and supporting source evidence for every value, then validate it before
publishing facts. Read structured page data where available. Supplier APIs can
later supplement coverage, especially for prices and availability that depend on
a specific quote. Send collectors option identifiers, criterion requests and
necessary scenario context, not the full member responses.

Before implementing, decide source access, accepted evidence standards, currency
and measurement conventions, freshness rules, storage permissions and the review
flow. Measure entity-match accuracy, unit/scope correctness, source coverage,
false confirmation rates, conflict detection, retrieval failures and cost per
completed request on independently reviewed examples.

This would automate fact acquisition progressively. It would not make arbitrary
option names or subjective qualities reliably factual without source evidence.
