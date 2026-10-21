# AI option research

Organisers enter options by name. Before publishing, the system looks each one up,
drafts questions for the group, and works out how every option fits each question.
All three steps are suggestions: the organiser sees and can change every result,
and nothing is shared with members until the form is published.

```text
Options entered ──► overviews (per option, in parallel)      ~5 s
                      kind → Google Places / web search / AI description
                ──► drafted questions (from overviews)        ~7 s
                ──► option fit (per question's own choices)   ~25 s
                      estimates stored as option facts with reason + sources
                ──► organiser edits ──► publish
```

## Configuration

Both keys live in `FSD/.env` (git-ignored); see [.env_example](../.env_example).

| Variable | Needed for | Without it |
| --- | --- | --- |
| `GEMINI_API_KEY` | Option kinds, web overviews, drafted questions, option fit, existing fact collection | Organisers enter details and questions themselves; the UI says research is unavailable |
| `GOOGLE_PLACES_API_KEY` | Venue photos, ratings, review summaries, price level, address, opening hours | Venues are described from web search only, without photos |
| `DECISION_RESEARCH_WORKERS` | Research slots in the dedicated worker (default 6, 1–8) | — |

Enable **Places API (New)** in Google Cloud Console, restrict the key to it, and set
a daily quota. Compose passes `GOOGLE_PLACES_API_KEY` only to `decision` (live place
cards and photos) and `decision-research`. The browser never receives either key.

After changing keys, recreate the services that read them:

```sh
docker compose -f compose.integration.yaml up -d decision decision-research
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
| `POST /v1/rounds/{draft}/research` | Admit `{"task": "overviews" \| "questions" \| "fit", "input": {...}}`. Draft rounds only (`409 FROZEN_HISTORY` once published). Returns a run, `202` while pending |
| `GET /v1/rounds/{draft}/research?run={id}` | Poll a run. Organiser-only, and only for runs admitted for this plan and round |
| `GET /v1/rounds/{round}/place?place_id=` | Live place card for display. Only for place IDs saved on this plan's options |
| `GET /v1/rounds/{round}/place-photo?name=` | Proxied photo bytes, with the same plan check |

Decision exposes the matching internal routes (`/internal/research`,
`/internal/places/{id}`, `/internal/places/{id}/photos/{ref}`). Research jobs use
the durable job queue with their own `research` kind and worker pool, so a slow web
search never delays recommendations or previews.

The frontend submits **one overview job per option** and renders each card as soon
as its job completes. Fit is requested only for questions whose facts are missing,
so adding a question later triggers lookups for that question alone.

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
- **Option fit becomes option facts** whose value is always one of the question's
  own choices, so the existing matcher compares like with like. Each fact keeps
  `context.estimated: true`, the model's one-sentence reason and up to three source
  links. The organiser sees **AI estimate** beside each one and can change it;
  organiser edits replace the estimate. Prices for budget questions are estimated
  the same way as a typical total cost per person.
- These facts carry `status: confirmed` so the published decision can rank, as the
  organiser reviewed them before publishing. The `estimated` flag preserves their
  origin. Exact, quoted claims still go through
  [Gemini fact collection](BACKEND_HARDENING.md#gemini-fact-collection) when stricter
  evidence is required.

## Measured on 2026-10-21

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
  re-sorting, fallbacks without Places, question validation, fit restricted to each
  question's own choices, budget amount parsing, and input validation before any
  provider call. Providers are mocked.
- `frontend/tests/lifecycle.spec.ts`: the browser journey uses fixed research
  responses, then publishes, invites, answers, ranks, confirms and RSVPs.
- Live provider calls are not part of the automated suites.

## Known limits

- Estimates come from web evidence and model judgement; they are not verified
  facts. Strongly subjective questions (mood, atmosphere) are the least reliable.
- Places matching uses one text-search result. Ambiguous names can resolve to the
  wrong venue; adding the website or a more specific name helps, and the card's
  address and Maps link make mismatches visible.
- Events are not checked against the plan's date range automatically.
- There is no per-plan spend limit; rely on the Google Cloud quota.
