# Regression testing

Run this before and after any refactor. If it passes before your change and after it, the behaviour the suite covers is unchanged.

```bash
scripts/regression.sh           # everything (the Docker stack must be running)
scripts/regression.sh --up      # build + start the Docker stack, then run everything
scripts/regression.sh --quick   # no Docker stack: unit tests, type-checks, UI-only browser tests
```

It prints a PASS/FAIL line per layer and exits non-zero if anything fails.

**One-time setup**

- Python: `python3 -m venv .venv && .venv/bin/pip install -r decision_service/requirements-test.txt`. The script finds `.venv` automatically, or point it at an interpreter with `PYTHON=/path/to/python`.
- Browsers: `cd frontend && npx playwright install chromium`. To use installed Chrome instead, set `PLAYWRIGHT_CHANNEL=chrome`.
- Full-stack tests need the Docker stack from `compose.integration.yaml` (frontend on `http://127.0.0.1:15173`, override with `FRONTEND_URL`) and the local Ollama model it is configured with. Web research is mocked inside the tests, so no Gemini key is needed for them.

## Layers

| Layer | Command | What it protects |
|---|---|---|
| Decision service (Python, ~390 tests) | `python -m unittest discover -s decision_service/tests -t .` | Preprocessing, scoring, fairness ranking, contracts, research parsing, ratings, importance, AI similarity (frozen per run), early close, date-poll summary, result views |
| Participation (NestJS, ~70 tests) | `cd participation-service-main && npm run prisma:generate && npm run typecheck && npx jest` | Answer validation per format (incl. ratings, importance, date polls), drafts, submit, freeze snapshots, early-close freeze |
| Planning (Go) | `cd planning-service && go vet ./... && go test ./...` | Access policy, snapshots, upstream client, confirmation date/time validation and retries |
| Frontend build | `cd frontend && npm run type-check && npm run build-only` | Types across components and services |
| Browser, UI-only | `cd frontend && npm run test:ui` | App shell, landing and join, remembered sessions and return links, creator recovery, research and fact review, member review, pending results. Every API call is mocked; runs at desktop, Pixel 7 and 320px widths |
| Browser, full-stack (`@stack`) | `cd frontend && npm run test:stack` | Real services end to end: create → invite → private answers → close → rank → confirm → RSVP; ratings + importance + AI-suggested weights changing the actual scores; deadline, reminders, early close; fact re-check; date poll and a dated confirmation with the calendar file; returning members not duplicated; public proxy hiding internal APIs |

CI (`.github/workflows/`) runs the three service suites, the frontend build, and the UI-only browser tests on every push. The `@stack` journeys need Docker and the local model, so run them locally with `scripts/regression.sh` before merging a refactor.

## Writing and changing tests

- **Select by what users see.** Use roles, labels and visible text (`getByRole('button', { name: 'Publish form' })`), not CSS classes. Some tests read a few classes such as `.board-rows` and `.date-poll-result` for layout checks. If a refactor renames them, update the selector, not the assertion.
- **Tag anything that needs the real services** with `{ tag: '@stack' }`. Untagged browser tests must mock `**/api/**` so they run in CI without services.
- **Full-stack helpers** live in `frontend/tests/support/stack.ts`. Use `newPerson`, `guest`, `mockResearch`, `publishForm`, `join`, `pick` and `submitFromReview`. Pass `research` to `publishForm`: it waits for the mocked fact lookup before publishing, so ranking never falls back to live web research.
- **Determinism.** Full-stack contexts use `Asia/Singapore` and `en-GB`, so dates and calendar times are stable. Prefer asserting exact outcomes (who wins, the percentages) over "something rendered".
- **A failing test is a behaviour change.** If you change behaviour on purpose, update the test in the same commit and say why in the commit message.
