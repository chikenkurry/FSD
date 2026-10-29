#!/usr/bin/env bash
# Full regression run across every service and the frontend.
#
#   scripts/regression.sh           all layers; the full-stack browser tests need the Docker stack running
#   scripts/regression.sh --up      build and start the Docker stack first, then run everything
#   scripts/regression.sh --quick   unit/contract tests, type-checks and UI-only browser tests (no Docker stack)
#   PYTHON=/path/to/python ...      use a specific interpreter that has decision_service/requirements-test.txt
#
# Exits non-zero if any layer fails, and prints a summary of every layer.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/compose.integration.yaml" -p what2do-integration)
STACK_URL="${FRONTEND_URL:-http://127.0.0.1:15173}"
MODE="full"
for arg in "$@"; do
  case "$arg" in
    --up) MODE="up" ;;
    --quick) MODE="quick" ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

results=()
failed=0
run() {
  local name="$1"; shift
  printf '\n\033[1m▶ %s\033[0m\n' "$name"
  if "$@"; then results+=("PASS  $name"); else results+=("FAIL  $name"); failed=1; fi
}

python_bin() {
  # Prefer a project virtualenv; fall back to python3 if it already has the test requirements.
  for candidate in ${PYTHON:-} "$ROOT/.venv/bin/python" "$ROOT/decision_service/.venv/bin/python" python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import jsonschema' 2>/dev/null; then echo "$candidate"; return; fi
  done
  echo ""
}

decision_tests() {
  local py; py="$(python_bin)"
  if [ -z "$py" ]; then
    echo "Python with decision_service/requirements-test.txt is required (e.g. python3 -m venv .venv && .venv/bin/pip install -r decision_service/requirements-test.txt)" >&2
    return 1
  fi
  (cd "$ROOT" && "$py" -m unittest discover -s decision_service/tests -t . -q)
}

participation_tests() {
  (cd "$ROOT/participation-service-main" && { [ -d node_modules ] || npm ci; } && npm run --silent prisma:generate >/dev/null && npm run --silent typecheck && npx jest --silent)
}

planning_tests() {
  if command -v go >/dev/null 2>&1; then
    (cd "$ROOT/planning-service" && go vet ./... && go test ./...)
  else
    # No local Go toolchain: use the same image the service builds with.
    docker run --rm -e PLANNING_TEST_DATABASE_URL -v "$ROOT/planning-service":/src -v w2d-gomod:/go/pkg/mod -w /src golang:1.27.2 sh -c 'go vet ./... && go test ./...'
  fi
}

frontend_checks() {
  (cd "$ROOT/frontend" && { [ -d node_modules ] || npm ci; } && npm run --silent type-check && npm run --silent build-only >/dev/null)
}

browser_ui_tests() {
  # UI-only specs mock every API call, so they run against a plain production build.
  (cd "$ROOT/frontend" && npm run --silent build-only >/dev/null && {
    npx vite preview --port 5197 --strictPort >/dev/null 2>&1 & local server=$!
    for _ in $(seq 1 30); do curl -s -o /dev/null http://127.0.0.1:5197/ && break; sleep 1; done
    FRONTEND_URL=http://127.0.0.1:5197 npx playwright test --grep-invert @stack --reporter=line; local status=$?
    kill "$server" 2>/dev/null; return $status
  })
}

browser_stack_tests() {
  if ! curl -s -o /dev/null "$STACK_URL/"; then
    echo "The Docker stack is not reachable at $STACK_URL. Start it with: scripts/regression.sh --up" >&2
    return 1
  fi
  (cd "$ROOT/frontend" && FRONTEND_URL="$STACK_URL" npx playwright test --grep @stack --reporter=line)
}

if [ "$MODE" = "up" ]; then
  run "Docker stack (build and start)" "${COMPOSE[@]}" up -d --build --wait
fi
run "Decision service: unit and contract tests" decision_tests
run "Participation service: type-check and unit tests" participation_tests
run "Planning service: vet and tests" planning_tests
run "Frontend: type-check and build" frontend_checks
run "Browser: UI-only specs (all device sizes)" browser_ui_tests
if [ "$MODE" != "quick" ]; then
  run "Browser: full-stack journeys (@stack)" browser_stack_tests
fi

printf '\n\033[1mRegression summary\033[0m\n'
printf '  %s\n' "${results[@]}"
exit $failed
