# AI option research

Organisers enter options by name. Before publishing, the system looks each one up,
drafts questions for the group, and collects reusable sourced option attributes.
The leader reviews the options once and can correct details or request fresh
research. Questions and publishing have no per-fact approval gate. Missing facts
are supplemented during Decision processing. Nothing is shared before publication.

```text
Options -> display overviews -> optional question drafts
        -> typed attribute requests -> grounded facts -> optional correction
Published facts -> missing evidence supplementation
                + member answers -> Decision interpretation -> algorithm ranking
```

The design and rejected alternatives are documented in
[Facts, meaning and deterministic decisions](../decision_service/docs/FACTS_AND_SEMANTICS.md).

## Configuration

Both keys live in `FSD/.env` (git-ignored); see [.env_example](../.env_example).

| Variable | Needed for | Without it |
| --- | --- | --- |
| `GEMINI_API_KEY` | Option kinds, web overviews, drafted questions and grounded fact collection | Organisers enter details and questions themselves; the UI says research is unavailable |
| `GOOGLE_PLACES_API_KEY` | Venue photos, ratings, review summaries, price level, address, opening hours | Venues are described from web search only, without photos |
| `DECISION_RESEARCH_WORKERS` | Research slots in the dedicated worker (default 6, 1–8) | — |

Enable **Places API (New)** in Google Cloud Console, restrict the key to it, and set
a daily quota. Compose passes `GOOGLE_PLACES_API_KEY` only to `decision` (live place
cards and photos) and `decision-research`. The browser never receives either key.

Without `GEMINI_API_KEY` the `decision-research` worker still starts and reports
healthy; each research job fails as `FACT_COLLECTOR_NOT_CONFIGURED`, which the UI
explains. CI relies on this, as it runs without provider keys.

After changing keys, recreate the services that read them:

```sh
docker compose -f compose.integration.yaml up -d decision decision-worker decision-preview decision-research
```

Rebuild **all** Decision services together after code changes
(`decision decision-worker decision-preview decision-research`). The API only admits
a job kind when a live worker reports the same implementation hash; rebuilding one
service alone makes the others reject that kind until they match.

## Option kinds

Each option, not each plan, gets a kind, so one session can mix them.

| Kind | Examples | Overview source |
| --- | --- | --- |
| `place` | Restaurant, park, gym, venue | Google Places details (photos, rating, price, address) **plus** a web summary and highlights, fetched in parallel |
| `destination` | Japan, Bali, Seoul | Web search summary, with Places photos |
| `event` | Festival, concert, race | Web search (dates, venue, price) |
| `activity` | Cycling, running, gym sessions | AI general description; no search, labelled as general |
| `other` | Products, services | Web search |

Gemini classifies all pending options in one call, using the option names, plan
category, decision question and region. Places then confirms `place` options: a text
search for `"<name>, <region>"` returns the best match. If that match is a region
type (country, city, administrative area), the option is re-sorted as a destination.
No match falls back to web search. The organiser can change the kind on the overview
card, which re-runs that option's lookup.

## Endpoints

Organiser-only POSTs go through Planning's guard; reads require plan membership.

| Planning route | Purpose |
| --- | --- |
| `POST /v1/rounds/{draft}/research` | Admit `{"task": "overviews" \| "questions" \| "facts", "input": {...}}`. Draft rounds only (`409 FROZEN_HISTORY` once published). Returns a run, `202` while pending |
| `GET /v1/rounds/{draft}/research?run={id}` | Poll a run. Organiser-only, and only for runs admitted for this plan and round |
| `GET /v1/rounds/{round}/place?place_id=` | Live place card for display. Only for place IDs saved on this plan's options |
| `GET /v1/rounds/{round}/place-photo?name=` | Proxied photo bytes, with the same plan check |

Decision exposes the matching internal routes (`/internal/research`,
`/internal/places/{id}`, `/internal/places/{id}/photos/{ref}`). Research jobs use
the durable job queue with their own `research` kind and worker pool. Organiser
lookups do not occupy recommendation/preview slots. Those workers may perform a
bounded missing-fact lookup as part of their own processing.

The frontend submits **one overview job per option** and renders each card as soon
as its job completes. Fact research requests only missing attributes. Questions sharing an attribute reuse its facts, and changing answer choices does not trigger another lookup.

## Data handling

- **Sent to providers:** option names and links, the decision question, category,
  the plan's location (as region) and currency. Member answers, rosters, private
  notes and plan descriptions are never included.
- **Google Places content is not stored.** Only the place ID is saved, in the
  option's `metadata.identity`. Cards, ratings and photos are fetched live through
  the routes above, with a short private browser cache. Photo author credits are
  shown on every photo; Google Maps links and review disclosures are shown where
  provided.
- **Web and AI summaries** (summary, highlights, price note, dates, area and source
  links) are saved as the option's `metadata.brief` and published in the member
  snapshot. Cards combine this stored brief with live Places details, so organisers
  and members see the same overview. Summaries are kept to two short sentences.
- **Scoring facts** use the grounded collector with typed attributes, exact excerpts,
  provider citations and retained qualifiers. They are independent of answer
  choices. Only option identities, links, region, attributes, currency/cost scope
  and an optional public correction note go to fact research. Neither question
  text nor member inputs are sent. Overviews are not factual evidence.
- Exact, cited, current, non-conflicting findings are eligible automatically with
  `verification=grounded_search`, distinct from human review. Conflicting and
  conditional claims remain unresolved. **Use my correction** records an organiser
  assertion. Fresh research preserves concurrent edits. Missing evidence stays unknown. See [core journey recovery](CORE_JOURNEY_RECOVERY.md).
- Decision interprets written answers and resolves synonyms against the fact
  vocabulary. It then passes typed meanings to the deterministic algorithm.
  New option rounds supplement missing typed attributes before interpretation,
  retaining the adopted evidence in the run for offline replay. Public results
  show the supplemented facts and citations. Old published rounds retain their
  existing choice-label policy.

## Historical measurements of the former flow (2026-10-21)

These timings predate the neutral-fact refactor and are not benchmarks of the current collector.

Live run with three Singapore restaurants (Odette, Burnt Ends, Lau Pa Sat):
overviews for all three in ~5–6 s, with Places ratings, price levels and nine
photos. Four drafted questions (budget, atmosphere, food style, dress code), and
option fit for every option and question in ~25–50 s total. The previous
single-job web search for the same options took 50–80 s.

A mixed run (restaurant, "Cycling at East Coast Park", "Japan", "ZoukOut festival")
classified each correctly. Japan was re-sorted from place to destination through
the Places region check. Times depend on provider latency and quota.

## Tests

- `decision_service/tests/test_research.py`: kind classification and region
  re-sorting, fallbacks without Places, written question validation, public fact-request isolation, neutral values,
  correction notes and input validation before any provider call. Providers are mocked.
- `frontend/tests/lifecycle.spec.ts`: the browser journey uses fixed research
  responses, then publishes, invites, answers, ranks, confirms and RSVPs.
- `decision_service/tests/test_fact_enrichment.py`: supplementation, conflict/expiry
  handling, private-payload isolation, correction preservation, shared cache and
  offline replay.
- Live provider calls are not part of the automated suites.

## Known limits

- Estimates come from web evidence and model judgement; they are not verified
  facts. Strongly subjective questions (mood, atmosphere) are the least reliable.
- Places matching uses one text-search result. Ambiguous names can resolve to the
  wrong venue; adding the website or a more specific name helps, and the card's
  address and Maps link make mismatches visible.
- Events are not checked against the plan's date range automatically.
- There is no per-plan spend limit; rely on the Google Cloud quota.
