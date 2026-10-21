# Frontend and connected system

The Vue app uses the Planning and Participation APIs through one origin. Decision
runs behind Planning; no internal service token or Gemini key enters the browser.
`feat/service-integration` combines the frontend and backend lifecycle work.

## Run everything

Install and start Docker Desktop, then open a terminal in `FSD/`. Keep your existing
root `.env`; on a fresh checkout copy `.env_example` to `.env` and fill its values.

```sh
docker compose -f compose.integration.yaml up -d --build --wait --wait-timeout 240
```

Open **http://localhost:15173**. This starts the frontend, Planning, Participation,
Decision API, recommendation/fact worker, preview worker and their PostgreSQL
instances. The migration job exits successfully after applying migrations; it is
not a continuously running service. First builds need internet access for images
and dependencies. The default `SEMANTIC_PROVIDER=ollama` uses an Ollama server
running separately on your computer, with `OLLAMA_MODEL` installed. Compose
connects through `OLLAMA_BASE_URL` (default `http://host.docker.internal:11434`);
it does not start Ollama. Set `SEMANTIC_PROVIDER=rules` explicitly for model-free
operation. Gemini is only needed for the separate fact collection feature.

```sh
# Check readiness and inspect failures
docker compose -f compose.integration.yaml ps
docker compose -f compose.integration.yaml logs --tail 100 frontend planning participation decision decision-worker

# Stop while retaining database volumes
docker compose -f compose.integration.yaml down
```

Run the `up` command again after pulling code changes. Do not add `--volumes` to
`down` unless you intend to delete all local data.

## Try the connected flow

1. Create a guest session with a display name. This creates a new identity; names
   are not passwords and do not grant access to another guest's data. The header's
   **Session details** can copy the user ID/token for resuming later. Keep them
   private. Sessions are stored in this tab's session storage, not in share URLs.
2. Create a form in five steps:
   - **Basics:** name, description, category, dates and location.
   - **Options:** the main question members answer (for example "Where should we
     celebrate?") and 2–8 options by name, each with an optional website. Press
     Enter to move to the next option.
   - **Overview:** AI looks each option up in the background, one job per option,
     usually within seconds. Venues get Google Places photos, rating, price level and
     address; destinations, events and activities get web or general summaries. Each
     card shows the detected type (Place, Destination, Event, Activity), which the
     organiser can change. This is what members will see.
   - **Questions:** AI drafts three to five questions from the overviews, such as
     budget, atmosphere, food style or dress code. Edit, remove or add questions;
     AI matches options to ranking questions automatically before review.
   - **Review:** check everything, including warnings for any option with an
     unknown fit, then publish. Nothing is shared before publishing.

   See [option research](../integration/OPTION_RESEARCH.md) for providers, keys,
   option kinds and data handling. Without `GEMINI_API_KEY` the steps still work;
   the organiser writes questions, and options without matching facts are flagged
   during review.
3. Create an invitation link. Open it in a private window or different browser.
   The invitee enters only their name, then sees the main question and the option
   overview cards before starting. Opening a second ordinary tab may copy session
   storage; use a private window to ensure a separate identity.
4. Members answer one question per page, with optional extras (options they can't
   join, a private note), then review their answers. The review page shows their
   private interpretation; requirements need explicit confirmation before **Submit
   response** unlocks. Each step saves the draft. Editing answers clears the review.
5. The organiser refreshes submission progress, closes collection, and calculates
   the recommendation. Closing freezes the roster/responses even if a member is
   incomplete, which can block ranking. Results show recommendations, alternatives,
   primary ties, option costs, times where present, and aggregate unavailable states.
6. The organiser confirms an eligible candidate. Members check for results and save
   their own RSVP against the confirmed selection version. Reloading retains backend
   state; the dashboard opens the latest round for an organiser's plan.

AI fit values are always one of the question's own choices, so the matcher compares
like with like. Budget questions are requirements compared with each option's
per-person cost (`max_cost`, Exact amount, in the chosen currency). Missing fits
leave that question unable to rank those options, and the Review step lists them.

## Mobile layout

Forms, controls, overview cards and candidate cards stack on narrow screens. Controls
have at least 44px target height. All five form steps remain visible in a compact grid; dashboard table
rows reflow into labelled entries instead of forcing sideways scrolling. Input text stays
readable and the viewport meta tag enables device-width layout.

For a real phone on the same trusted Wi-Fi, set the frontend listener explicitly:

```sh
FRONTEND_BIND=0.0.0.0 docker compose -f compose.integration.yaml up -d frontend
```

Open `http://<your-computer-LAN-IP>:15173` on the phone. Only the frontend port
needs to be reachable. Planning/Participation keep their loopback-only debug ports;
Decision is not host-published. This is a local development HTTP setup; use HTTPS
for a deployed app. Clipboard APIs can be unavailable over LAN HTTP, so select and
copy the invitation field manually. On Windows PowerShell set
`$env:FRONTEND_BIND="0.0.0.0"` before the Compose command.

## Frontend development

Keep the backend stack running, then in a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies the same `/api/planning` and
`/api/participation` paths to local ports 18080/13002. No browser CORS exceptions
or changes to the API token are needed. Docker builds use Node 22; for a host
setup use a supported recent Node version compatible with `package.json`.

```sh
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

The browser tests target the Compose UI at port 15173 and create isolated synthetic
plans. They run desktop, Pixel-sized and 320px phone viewport journeys through creation, invitations,
private requirement review, submission, recommendation, confirmation and RSVP, and
check page overflow and internal-route blocking. Set `FRONTEND_URL` for a different
UI origin. `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` uses installed Chrome if
managed-network certificates prevent the bundled browser download. Tests replace AI
research with fixed responses, so they never call Gemini or Places, and they do not
record traces containing session tokens.

Verified on 2026-10-21: nine browser checks passed across the three viewports with
the AI-assisted creator and step-by-step member flow; 344 Decision tests (including
`test_research.py`), Planning's Go tests and all 14 connected HTTP journeys passed.
A separate live run with real Singapore venues returned Places overviews in about
5 seconds, drafted questions and option fit, published, and showed nine photos to an
invited member.

Verified on 2026-10-19: the production Docker build/type check passed; six browser
checks passed across desktop, Pixel-sized and 320px mobile viewports, including a
temporary publish outage/retry without duplicate plan creation. The journey also
checks saved RSVP restoration after reload. A loading race found during testing
was fixed by keeping the RSVP selector disabled until the saved response arrives.
All 14 connected backend HTTP journeys and 343 Decision tests with PostgreSQL
enabled passed. Planning's Go tests passed during its Docker build. All nine
long-running Compose services were healthy; the migration job exited successfully.

## Design choices and remaining scope

- Nginx serves the compiled app and proxies the two public services. It resolves
  Docker service DNS at request time, so backend container replacement does not
  require rebuilding the frontend. Internal paths are blocked. Same-origin proxying
  avoids per-handler CORS policies and keeps browser configuration consistent.
- Guest sessions use existing backend credentials. The prototype's username-only
  fake login and unused password form were removed; no new identity provider or
  password database was introduced. Revocation is performed on sign-out.
  Browser API calls and proxy responses disable caching of private response data.
- Publishing uses existing plan, option, question and round APIs, keeping returned
  IDs in the current creator so acknowledged partial work can be retried. There is
  no distributed transaction across these calls. An ambiguous network timeout can
  still require checking saved drafts; creation is not universally idempotent.
- Lifecycle authority and revision checks stay server-side. The UI retains an
  operation ID for confirmation retries and polls jobs for a bounded period; a
  running job can subsequently be read with Refresh status.
- Email added on the frontend branch is now backed by migration 004. It defaults
  to empty for guest users; a partial case-insensitive unique index applies only
  to nonempty addresses. Existing usernames, users and sessions are preserved.
- The form creator currently publishes ordinary **options** decisions. Its date
  range/location are context, not generated time slots or enforced availability.
  AI research is organiser-side and pre-publication; every result is a suggestion
  the organiser can change. Dedicated scheduled/scenario creation, rich multi-window
  availability editing, draft recovery across browser sessions, round-definition
  editing/reopening, a review screen for quoted Gemini fact claims, and external
  authentication remain separate UI work.
  Existing API routes continue to provide these backend capabilities. Existing
  multi-window responses are protected from edits by this limited renderer.

The previous hardening branch is included in this branch's history. Its lifecycle
guards, immutable snapshots, PostgreSQL queue, private result filtering and
recommendation contract remain authoritative. The merge retained the guards over
the prototype's per-handler CORS additions; browser requests instead use the proxy.


## UI design

The interface serves professional organisations and informal groups through one
consistent visual system. [PRODUCT.md](../PRODUCT.md) records the confirmed scope;
[DESIGN.md](../DESIGN.md) records the implemented tokens, layout and components.
The redesign uses [Impeccable](https://github.com/pbakaus/impeccable)'s guidance for
task-oriented interfaces: familiar controls, clear hierarchy, purposeful colour,
private/shared state separation and responsive composition.

- A single navy application header replaces duplicate navigation. Guest-session
  details remain a secondary disclosure rather than competing with the task.
- Self-hosted Public Sans provides one readable type family without a font CDN
  request. Its SIL Open Font License is included in `public/fonts/OFL.txt`.
- Shared CSS tokens and controls replace repeated button and field rules. Local
  component CSS owns layout. No component framework or animation runtime was added:
  Vue transitions and CSS keyframes cover the motion, and another system would add
  dependency and migration cost without a required feature.
- Green marks primary actions, current steps and positive decision states. Status
  labels always include text; colour alone never communicates the lifecycle.
- The dashboard keeps a table on desktop and presents labelled entries on phones.
  Search/status filters operate on the loaded organiser forms; they are not a new
  server-wide search or pagination feature. The API currently loads at most 20.
- The creator asks for as little as possible: names, the main question and option
  names. AI research fills in overviews, questions and option fit, each visibly
  labelled (photo credits, "From the web", "General description by AI", "AI
  estimate") so organisers can tell sourced content from model judgement. Inline
  validation keeps recovery beside the work.
- Invited members see a name-only join screen, then the main question with option
  overview cards, then one question per page, extras, review and a confirmation.
  Pages slide in the direction of travel. Members see overviews, not the internal
  comparison facts used for ranking.
- The organiser's round workspace shows the collection/review/confirmation sequence,
  response progress, recommendation cards with fit bars and the RSVP. Rankings,
  privacy and revision checks still come from the same backend contracts.
- Motion uses shared duration and easing tokens: page and step transitions, list
  enter/leave, disclosure expansion, meters that fill once, a drawn confirmation
  check and loading shimmers. `prefers-reduced-motion` removes all of it.
- Neutral language and restrained styling avoid a separate business/casual mode.
  Decorative gradients, fake metrics, stock illustrations and marketing claims do
  not help users finish these tasks and were not introduced.

The UI refresh does not add organisation accounts, SSO, tenant isolation or company
administration. Those remain separate product capabilities despite the broader
intended audience. Responsive checks use Chromium device emulation; real iOS,
Android hardware and assistive-technology verification remain outside those checks.

To capture synthetic UI screenshots while running the browser tests:

```sh
PLAYWRIGHT_CHANNEL=chrome UI_CAPTURE_DIR=/tmp/what2do-ui npm run test:e2e
```

Captures include desktop/mobile entry, empty, creator, response review, results,
RSVP, populated dashboard and long-content states. Session tokens are not captured
in traces; the session disclosure remains closed in these screenshots.


Verified on 2026-10-20 after the UI redesign: the production Docker build and
TypeScript check passed. All nine Chromium browser checks passed across desktop,
Pixel-sized and 320px viewports. The checks cover the full two-member lifecycle,
publish retry, private confirmation, saved RSVP restoration, search and status
filtering, inline validation, category mapping, long titles/names, list-error
recovery, skip-link behavior and session-menu placement. The API-boundary checks
also passed. Impeccable's mechanical detector reported no findings on the scanned
UI sources. These checks are not a full accessibility certification.


## Refresh recovery and incomplete comparisons

Creator fields, the current step, acknowledged plan/option/question/round IDs and
web-written research briefs are checkpointed synchronously in session storage.
Returning from the dashboard resumes the tab's current draft; publishing clears
that checkpoint. In-flight research run IDs are keyed by user, round, task and
exact input, so refresh polls the existing run rather than blindly starting another.
Completed overview identities are retained; renamed options or changed context are
researched again. Google Places details/photos are not checkpointed: they reload
from the live place endpoint.

Member answers, optional extras and current page are checkpointed before Next as
well as saved to the server on Next. Browser edits are restored only when both the
server revision and form definition still match. A newer revision/closed round wins.
Private interpretation and requirement confirmation are never restored as approved;
a refreshed review is checked again. Sign-out clears the user's tab checkpoints.
If storage is full or unavailable the UI says so. This supports refresh in the same
browser tab, not cross-device recovery or recovery after clearing/closing the tab.
Ambiguous network failures before a creation ID is returned remain subject to the
existing server API's idempotency limits.

“Worth checking” lists missing comparison facts, not missing display overviews.
Grounded extraction must receive the original option keys, criterion IDs and exact
choice labels alongside search evidence. Unsupported claims remain missing rather
than invented. Review displays incomplete/failed research and offers a retry;
unresolved questions can be revised or explicitly changed to Context only.
Missing required facts can block ranking, so the UI does not promise the scorer
will simply ignore them. Importance ratings cannot be treated as a venue attribute;
question drafting asks for preferences over evidenced option attributes instead.

Verified on 2026-10-21: production build/type check passed; 18 Chromium checks
passed across desktop, Pixel-sized and 320px viewports. Tests refresh partial
creator edits, pending overview jobs, drafted questions, final review and a failed
publish attempt, then finish the real two-member lifecycle without duplicate plans.
Member refresh checks cover unsaved answers, extras, review position and explicit
re-confirmation. Focused fixtures verify empty-fit retry and storage-full feedback.
Nine Python research tests passed in the application’s Python 3.12 container,
including retaining the option/criterion/choice mapping during grounded extraction.
Live restaurant claim accuracy and a successful paid Gemini retry are not claimed
by these deterministic regression tests.
