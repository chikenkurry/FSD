# Facts, meaning and deterministic decisions

The core flow separates public evidence, member meaning and ranking. The goal is
for AI to help the system understand inputs while the decision policy remains
explicit, testable and reproducible.

## Ownership

| Stage | Owns | Does not own |
| --- | --- | --- |
| Gemini grounded collector | Public option identities, requested typed attributes, cited source excerpts and qualifiers | Member preferences, requirement strength, candidate utility or final ordering |
| Decision preprocessing / Ollama | Interpretation of member wording, scoped synonym equivalence, typed preferences and explicit requirements | Creation or confirmation of option facts, candidate scores |
| Algorithm | Feasibility, numeric boundaries, utility, weights, group fairness, ties and stable ordering | Web research or language-model calls |
| Organiser / member | Organiser reviews option identity/overview once and may correct details; each member checks their interpreted requirements | LLM-generated scores or winners |

Overviews and optional question drafting remain organiser-facing conveniences.
They cannot establish a scoring fact. Google Places content remains display-only;
an attractive summary or a high rating cannot fill a missing comparison value.

## Reusable facts rather than question-choice classification

A fact is keyed by option and attribute, for example `cuisine`, `atmosphere` or
`max_cost`, with a value type and optional unit. Its value comes from evidence,
not the list of answers a question offers. An option may have atmosphere `calm`
even when a question offers `Peaceful` and `Social`.

The old `fit` research task, choice filtering, `FitFact` response and frontend
choice-tag editors are removed. The replacement `facts` task accepts option
identities and 1–8 typed attributes, yielding at most 64 requested pairs. It calls
the existing grounded collector instead of introducing another extraction stack.

Fact research sanitises its payload before calling Gemini. It includes identities,
source links, region, requested attributes, currency/cost scope and an optional
bounded correction note. Question wording, answer choices, participant answers,
rosters, unverified overview summaries and the main decision question are excluded.
A correction note is a request to verify, not evidence.

The collector searches, extracts only from that search text, and checks identity,
type, unit, excerpt and provider citation support. Unsupported claims stay unknown.
It retains conditions and expiry rather than turning “from” or “up to” prices into
exact amounts. Conflicting findings are presented for explicit organiser selection;
the UI does not silently pick a winner. Conditional claims require correction or
verification before approval. Draft saving preserves unknowns and review metadata.

The leader reviews the options in **Overview** once. An optional supporting-facts
editor shows citations, accepts corrections and offers fresh research. Exact,
current, cited, non-conflicting findings are eligible automatically under the
`grounded-option-facts-v1` policy. Conditional, unsupported and conflicting claims
remain unresolved. **Use my correction** explicitly records an organiser-supplied
value. There is no per-question fact approval checklist or publishing gate.
The new policy also disables the legacy semantic-provider option-tag suggestion
call: an unavailable fact collector never falls back to Ollama's memory of an option.

A fact signature covers the option identity, location, overview context, attribute
type and unit. Editing a question's title or choices leaves the fact intact.
Changing its option identity invalidates the old fact. Slow
responses cannot overwrite newer edits. Duplicate questions about one attribute
share a fact, so they do not cause another option/choice classification request.

## Automatic supplementation

For new `facts-v1` option rounds, preview and recommendation workers supplement
missing typed attributes before semantic interpretation. Requests are derived
from declared attribute mappings, existing attributes used by broad written
questions, and a limited Participation budget when present. At most 64 public
option/attribute pairs are collected in one batch. Untyped, unidentified or
date-scoped scenario facts remain explicit gaps rather than guessed requests.

Only sanitised option identity, region, attribute/type/unit and currency/cost scope
reach Gemini. Member answers, budget caps, private notes, rosters, question text
and answer choices stay inside the services. An exact amount and cost scope are
required for a budget comparison; a headline “from” price cannot satisfy it.

An exact, cited, current finding is adopted only when there is one distinct value
across the returned claims. `status=confirmed` means eligible for deterministic
comparison under this evidence policy. `context.verification=grounded_search` and
`reviewed=false` distinguish it from human review. This verifies citation support
and applicability checks; it cannot independently prove that a publisher or an
extraction is correct. Existing confirmed organiser corrections are preserved.

The shared durable cache reuses identical public research within a six-hour
bucket, keyed by identity, requested types/units, policy and collector/model
revision. Claim expiry is checked again on use. Conflicts, unavailable providers
and absent evidence retain an unresolved result. Collection is bounded by the
existing worker deadline and does not loop until a favourable answer appears.

Supplementation never changes the frozen Planning snapshot. The run records the
collection and applied facts; `replay_facts()` rebuilds its executed factual input
offline. Public results expose an allowlisted `supplemented_facts` array, displayed
as **Evidence added during calculation**. Original member inputs and internal
research diagnostics remain private. Legacy rounds retain their previous policy.

## Interpreting answers

The creator supports scored written preferences and requirements. Its comparison
settings separate the fact format from the answer format: a written response can
refer to a categorical fact. A general written question can use all researched
attributes, including multiple criteria in one answer.

For example, given sourced prices and atmosphere/cuisine facts:

> I must stay below SGD 100; I prefer somewhere peaceful and Italian.

Decision extracts a strict budget boundary and separate atmosphere/cuisine
preferences. It can map `peaceful` to an established `calm` fact value through a
scoped equivalence assessment. It preserves the member's clause evidence and
negation. One bounded repair request is permitted if the provider paraphrases its
evidence. The repair schema restricts evidence to literal answer spans; the
repaired response must still pass the same exact-span check. A
second failure is reported as a provider error. The model is not asked which
restaurant should win.

Exact typed values and known labels need no model call. Unresolved wording uses
the configured semantic provider. Ambiguous or unsupported meanings ask for
clarification. A known attribute without sufficient evidence produces a missing-fact
request; undeclared or ambiguous attributes need clarification. An interpretation
never creates a claim that an option possesses that attribute.

Members see the interpreted values and requirements. Model-derived requirements
need explicit confirmation against the current saved response revision. Submission
in the new flow is blocked while interpretation is pending, unavailable or
ambiguous. Inferred requirements in a soft written answer receive the same
confirmation control as a dedicated requirement question.

Preview polling tolerates model latency while showing status. Leaving review lets
the member edit; a generation/revision fence discards late results for an old
response. The durable server job remains reusable for that exact revision.

## Algorithm boundary and replay

The algorithm receives a validated typed packet. It makes no model calls. It
checks confirmed facts against requirements first, then applies the declared
categorical, tag-overlap or numeric utilities and the configured fairness policy.
A missing or unconfirmed required fact produces an unresolved decision rather
than an invented match. “Below 100” excludes an option costing exactly 100.

Semantic assessments are recorded with the immutable snapshot identities,
processing version, interpretation policy and model identity. Replaying the same
recorded meanings and recorded supplemented facts reproduces preparation without
a model or web call. This distinguishes
the design from asking an LLM to choose, score or justify a winner after the fact.

## Compatibility and operation

New frontend publications set `interpretation_policy: facts-v1`. Old published
rounds without the field keep `choice-labels-v1`: their declared-choice behaviour
is preserved. A new round can adopt the new policy without rewriting history.
The processor version is `sparse-v12`, preventing reuse of earlier preprocessing
artifacts under a changed implementation. No database migration is needed.

Rebuild all Decision roles together, plus Planning and the frontend:

```sh
docker compose -f compose.integration.yaml up -d --build --wait --wait-timeout 240
```

Ollama remains the default semantic provider and runs separately on the host.
`rules` supports unambiguous structured answers but cannot interpret arbitrary
prose. The frontend reports that failure and asks for clarification; it does not
silently turn a scored written answer into context only.
Compose supplies the Gemini key to research, recommendation and preview workers;
the browser and API admission process never receive that key.

## Alternatives and tradeoffs

- **Question-dependent Gemini classifications:** convenient for exact matching,
  but couple facts to wording, duplicate interpretation responsibilities and
  trigger repeated research when choices change. Removed from the core flow.
- **LLM-generated scores or winners:** flexible prose output but no dependable
  enforcement of exact boundaries or reproducible fairness calculations. Rejected.
- **Embedding similarity as the final score:** useful for retrieval, but similarity
  alone cannot establish a budget limit or prove a capability. No new vector store
  or embedding service is introduced.
- **Model calls for every structured answer:** unnecessary latency for exact known
  values. The existing deterministic fast path is retained.
- **Requiring facts for every question before publication:** adds repeated leader
  work and makes background search an onboarding gate. Replaced by a single
  option review and bounded supplementation; final ranking still requires enough
  evidence to apply its comparisons honestly.
- **Deleting the legacy processor:** would reinterpret stored rounds and remove
  supported historical contracts. Only the superseded research/client path is
  deleted; existing execution adapters remain supported.

Automated coverage includes public research payload isolation, neutral values that
are absent from question choices, confirmation of mixed written answers, strict
budget feasibility, missing-fact blocking and offline semantic replay. Browser
fixtures cover editing/research races, reusable facts, refresh recovery and member
confirmation. Provider fixtures test behaviour deterministically; they do not
establish the accuracy of every live search or model response.

## Verification on 22 October 2026

- 368 Decision tests passed, including PostgreSQL storage, independent HTTP
  workers, semantic grounding, missing-fact supplementation and offline replay.
- 17 HTTP integration journeys passed, including publication with missing
  evidence and an explicit unresolved result when option identity is unavailable.
- All 42 browser checks passed across desktop, mobile and 320-pixel widths,
  including the full publish-to-RSVP lifecycle, reopened rounds, pending research,
  missing-fact publication, saved corrections and evidence-link wrapping.
- Frontend type checking, unused-symbol checks and the production build passed.
- A live two-member Ollama journey interpreted mixed written answers, confirmed
  the strict budget requirement, closed the round and ranked deterministically.
  A venue costing exactly SGD 100 was excluded for “below SGD 100”.
- One bounded live Gemini Search check supplemented the cuisine of Griglia Open
  Fire Italian Kitchen - Katong with two citations and no collection issues.
  This is a smoke check of the configured provider, not a claim that every
  restaurant attribute or every search response is correct.

The optional `python3 integration/smoke_semantic_lifecycle.py` script exercises
Ollama against synthetic facts and answers through the running services. It
creates an isolated test plan and makes no Gemini calls.
