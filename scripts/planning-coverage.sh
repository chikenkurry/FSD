#!/usr/bin/env bash
# Measures Planning's statement coverage from its unit tests plus the end-to-end journeys.
#
#   scripts/planning-coverage.sh           unit tests, HTTP lifecycle and full-stack browser journeys
#   scripts/planning-coverage.sh --http    unit tests and HTTP lifecycle only (no Ollama or browser needed)
#   scripts/planning-coverage.sh --report  only stop Planning and report; the stack must already run with
#                                          compose.coverage.yaml and the journeys must have run (used by CI)
#
# Planning is rebuilt with Go coverage instrumentation for the run and rebuilt normally afterwards.
# The unit tests run in the Go build image against a throwaway PostgreSQL database, so the
# PostgreSQL-backed access tests are included. Results are written to .local-data/coverage/planning.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/.local-data/coverage/planning"
PROJECT=(-p what2do-integration)
BASE=(docker compose -f "$ROOT/compose.integration.yaml" "${PROJECT[@]}")
COVERED=(docker compose -f "$ROOT/compose.integration.yaml" -f "$ROOT/compose.coverage.yaml" "${PROJECT[@]}")
GO_IMAGE=golang:1.27.2
MODE="${1:-full}"
journeys_failed=0
case "$MODE" in full|--http|--report) ;; *) sed -n '2,11p' "$0"; exit 2 ;; esac

if [ "$MODE" != "--report" ]; then
  rm -rf "$OUT"
  mkdir -p "$OUT/e2e"
  chmod 777 "$OUT/e2e" # Planning runs as a non-root user inside its container.
  # Always return the stack to a normal Planning build, even after a failure.
  trap 'echo "Restoring the normal Planning build…"; "${BASE[@]}" up -d --build --wait planning >/dev/null' EXIT
  echo "Building Planning with coverage instrumentation…"
  "${COVERED[@]}" up -d --build --wait planning
  # A failing journey still leaves valid counters, so report coverage and fail at the end.
  python3 "$ROOT/integration/test_http_lifecycle.py" || journeys_failed=1
  if [ "$MODE" = "full" ]; then
    (cd "$ROOT/frontend" && npx playwright test --grep @stack --reporter=line) || journeys_failed=1
  fi
fi

# Counters are flushed when the process exits normally, so stop Planning gracefully.
"${COVERED[@]}" stop planning >/dev/null
rm -rf "$OUT/unit" && mkdir -p "$OUT/unit"

network="w2d-coverage-$$"
docker network create "$network" >/dev/null
cleanup_db() { docker rm -f "$network-db" >/dev/null 2>&1 || true; docker network rm "$network" >/dev/null 2>&1 || true; }
trap 'cleanup_db; [ "$MODE" = "--report" ] || { echo "Restoring the normal Planning build…"; "${BASE[@]}" up -d --build --wait planning >/dev/null; }' EXIT
docker run -d --rm --name "$network-db" --network "$network" \
  -e POSTGRES_USER=planning -e POSTGRES_PASSWORD=planning -e POSTGRES_DB=planning postgres:16 >/dev/null
until docker exec "$network-db" pg_isready -U planning -d planning >/dev/null 2>&1; do sleep 1; done

docker run --rm --network "$network" -v "$ROOT/planning-service":/src:ro -v "$OUT":/out -v w2d-gomod:/go/pkg/mod \
  -e "PLANNING_TEST_DATABASE_URL=postgres://planning:planning@$network-db:5432/planning?sslmode=disable" \
  "$GO_IMAGE" sh -c '
    set -e
    cp -r /src /tmp/planning && cd /tmp/planning
    go test -count=1 -cover -coverpkg=./app/... ./... -args -test.gocoverdir=/out/unit >/dev/null
    total() { go tool covdata textfmt -i="$1" -o /tmp/profile.out && go tool cover -func=/tmp/profile.out | tail -1 | awk "{print \$NF}"; }
    echo
    echo "Planning statement coverage"
    printf "  %-34s %s\n" "Unit tests" "$(total /out/unit)"
    printf "  %-34s %s\n" "End-to-end journeys" "$(total /out/e2e)"
    printf "  %-34s %s\n" "Combined" "$(total /out/unit,/out/e2e)"
    echo
    go tool covdata percent -i=/out/unit,/out/e2e | sed "s#planning-service/app/#  #"
    go tool covdata textfmt -i=/out/unit,/out/e2e -o /out/combined.out
  '
echo "Profile: $OUT/combined.out (view with: cd planning-service && go tool cover -html=../.local-data/coverage/planning/combined.out)"
if [ "$journeys_failed" = 1 ]; then
  echo "Some end-to-end journeys failed; the coverage above includes only the code they reached." >&2
  exit 1
fi
