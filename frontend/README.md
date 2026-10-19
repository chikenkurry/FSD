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
and dependencies. The default `SEMANTIC_PROVIDER=rules` requires no Ollama server.
Gemini is only needed for the separate fact collection feature.

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
2. Create a form. Add 1–8 options and facts, then questions tied to the same
   criteria. For a simple example add Cafe with `environment=indoor` and Park with
   `environment=outdoor` (Category facts), then a Single choice question with
   criterion `environment` and choices `indoor`, `outdoor`. Include the source of
   each fact. A successful publish opens the real round workspace.
3. Create an invitation link. Open it in a private window or different browser,
   create another guest session, and join. Opening a second ordinary tab may copy
   session storage; use a private window to ensure a separate identity.
4. Both members answer the form. **Save & review interpretation** shows only that
   member's interpretation. Requirements need explicit confirmation of the saved
   revision. Editing answers clears the review. **Submit response** persists the
   response; there is no simulated success state.
5. The organiser refreshes submission progress, closes collection, and calculates
   the recommendation. Closing freezes the roster/responses even if a member is
   incomplete, which can block ranking. Results show recommendations, alternatives,
   primary ties, option costs, times where present, and aggregate unavailable states.
6. The organiser confirms an eligible candidate. Members refresh and save their
   own RSVP against the confirmed selection version. Reloading retains backend
   state; the dashboard opens the latest round for an organiser's plan.

Use matching units/types across facts and questions. Numeric preferences have an
explicit tolerance around the preferred value. Costs use `max_cost`, Exact amount,
unit equal to the chosen currency, and per-person total scope. Missing facts block
ranking when they are needed; the UI does not invent evidence. Budget range choices
are category preferences, not numeric budget caps. Number requirements currently
use equality; other hard comparison rules remain available through the API.

## Mobile layout

Forms, controls and candidate cards stack on narrow screens. Controls have at
least 44px target height. Form steps scroll within their own row; dashboard tables
scroll within their container instead of forcing the page wider. Input text stays
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
managed-network certificates prevent the bundled browser download. Tests do not
call Gemini and do not record traces containing session tokens.

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
  Dedicated scheduled/scenario creation, rich multi-window availability editing,
  draft recovery across browser sessions, round-definition editing/reopening,
  Gemini fact review screens and external authentication remain separate UI work.
  Existing API routes continue to provide these backend capabilities. Existing
  multi-window responses are protected from edits by this limited renderer.

The previous hardening branch is included in this branch's history. Its lifecycle
guards, immutable snapshots, PostgreSQL queue, private result filtering and
recommendation contract remain authoritative. The merge retained the guards over
the prototype's per-handler CORS additions; browser requests instead use the proxy.
