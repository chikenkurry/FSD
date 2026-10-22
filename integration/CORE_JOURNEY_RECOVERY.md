# Completing and recovering a decision

The normal journey is create → review comparison facts → publish → collect and
privately review responses → close → calculate → confirm → RSVP. This change
completes the recovery paths around that journey without changing its ranking
policy or the ownership of Planning, Participation and Decision data.

## Fact correction and fresh research

The creator's Overview step offers **Correct this overview** and **Research
again** for each option. An edited summary is labelled as organiser corrected;
it does not pretend to be unmodified Google Places or web content. Google Places
ratings, photos and credits remain display-only provider content.

The Review step shows a comparison table grouped by option and question. The
organiser can edit each value, record a source/verification note, inspect research
citations and request fresh research with a bounded correction note. Only public
option information and the organiser's note reach Gemini; member answers and
private notes are not part of research requests.

Research facts start as `estimated`. Saving a draft preserves that state. Checking
the approval box writes `status=confirmed` and `context.reviewed=true`. Earlier
AI estimates that were saved as confirmed without this explicit approval are
presented for review. Publishing through the creator requires valid, approved
facts for every scored/required question and option. A context-only question
needs no comparison fact. The low-level API still supports incomplete definitions
for diagnostic workflows; this creator check is not a new claim of independent
verification by the system.

An input signature covers the option, summary, source identity, question, choices,
units, currency and decision context. Changes invalidate earlier approvals. Slow
research is applied only when both the definition and the current fact still
match the version that was researched. It cannot replace a correction made while
the request was running. Unchanged saved overviews are reused when a draft is
loaded, including organiser corrections.

Explicit **Research again** adds a fresh request identity, bypassing reuse of a
previous completed research job. Automatic retries/resumption retain that same
identity. The existing value remains visible while research runs; requesting
verification removes its earlier approval. No-evidence and failed requests keep
the value and explain what happened. A successful replacement requires approval
again. Empty research results are not evidence that an attribute is absent.

An organiser's approval is a human assertion, not proof that a web claim is true.
Dietary and other safety-sensitive requirements should be checked with a reliable
source or the provider. The separate quoted-claim collection/acceptance APIs retain
their stricter provenance checks.

## Closing only complete responses

Readiness shows the current Planning roster with complete/incomplete/stale states.
Only status and display names are shared with the organiser, not private answers.
The close control remains disabled until every current member is complete. The
readiness endpoint is advisory: submission completeness is checked again under
Participation's exclusive round lock when Planning sends `requireComplete=true`.

An incomplete freeze does not write a response snapshot. Participation commits a
terminal rejection record keyed by round and operation before returning
`409 RESPONSES_INCOMPLETE`. Planning restores collection only for that exact
attempt and creates a fresh freeze operation identity for the next attempt.

The rejection record is necessary for concurrent replicas/reconcilers: a delayed
retry of a rejected command must remain rejected even if members submit later.
An in-memory flag or a preflight count alone would allow that retry to freeze a
different response set after collection had been restored. Completed freezes
retain their existing idempotency and immutable snapshot rules. Other upstream
failures remain pending/recoverable rather than being optimistically rolled back.

The internal freeze API keeps its historical non-strict mode when
`requireComplete` is absent. Integrated Planning closure always requests the
strict check. PostgreSQL stores rejection records for the lifetime of the round.

## Reopening and history

The organiser can choose **Revise in a new round** from reviewing or confirmed
rounds. The existing idempotent reopen API creates a new draft round; the creator
loads the existing editable plan/options/questions and wizard metadata from
Planning. The previous published definition, recommendation, selection and RSVPs
remain attached to the old round.

The new published form carries `previous_round_id`. Members may explicitly copy
their own earlier answers into a new draft. Copying preserves the existing
backend rules: it does not overwrite a current draft, does not copy another
member's response, and removes earlier interpretation confirmations. Members must
review the new definition, update invalid choices and confirm requirements again.
Historical round views disable editing and RSVP writes.

## Result updates

The workspace reads the authoritative stored run after mounting, including after
a browser refresh. Pending runs continue polling without enqueuing another job.
Calculation and confirmation updates are discovered automatically. Polls do not
overlap, pause while the document is hidden and stop after confirmation/unmount.
Collection polls avoid fetching result/selection endpoints before those resources
can exist. Failed status requests retain the last known state and retry with a
visible message. The server job can continue independently of the browser.

Polling was chosen over WebSockets because the workflow already has durable jobs
and read endpoints, and sub-second push delivery is not a product requirement.
This avoids another connection lifecycle and notification delivery mechanism.

## Server draft recovery and joined plans

The creator debounces saves and serialises its save/research work. Plans, options
and questions remain in their existing authoritative tables. `plan_rounds` stores
only wizard metadata (currency, main question, location and current/visited step),
plus an optional source round reference. We deliberately avoid a second complete
form document that could disagree with those tables.

The UI reports server save failures and retains tab-local checkpoints for pending
edits. A saved draft can be reopened from My forms after clearing the browser
checkpoint or resuming the same guest session in another browser. On load, the
server's latest round identity is checked before reusing local edits. Untitled
drafts before a name/category is provided, and changes not yet acknowledged by the
server, still rely on the current tab checkpoint. Multi-request draft saving is
not a distributed transaction; ambiguous initial creation failures remain a
documented limitation.

The dashboard uses the caller-scoped membership list, so it includes organised
and joined plans (currently capped at 100). A member opens the latest published
round while an organiser can resume the latest draft. Guest sessions still use
the existing user ID/session token; this does not introduce accounts or SSO.

## Migrations and checks

- Planning: `005_creator_recovery.sql` adds nullable wizard metadata and a source
  round reference. Existing published snapshots need no rewrite.
- Participation: `20261021000000_rejected_freezes` adds terminal rejected-command
  records. Existing response/snapshot rows are preserved.
- Tests cover strict close rejection/retry, delayed rejected-command replay,
  organiser-only draft metadata, joined-plan access, preserved old forms, server
  recovery without browser checkpoints, manual fact correction/fresh research,
  pending-result resumption and automatic confirmation updates.

Run the standard Compose startup to build the changes and apply both migrations.
Run `python3 integration/test_http_lifecycle.py`, Participation's unit tests, and
the frontend Playwright suite across desktop and mobile projects. Research/browser
fixtures are synthetic; those checks do not establish live provider accuracy.

Verified locally on 22 October 2026: 355 Decision tests (including PostgreSQL
store tests), 65 Participation unit tests, 15 HTTP integration journeys and all
27 Playwright tests across desktop, mobile and 320-pixel mobile widths passed.
Planning's Go tests and build, the frontend type check and production build,
and `git diff --check` also passed. The local Compose stack was rebuilt and both
additive migrations were applied.
