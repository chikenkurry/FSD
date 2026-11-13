package handler

// Shared helpers for the handler tests.
//
// Database-backed tests run against a real PostgreSQL database, because the
// repositories depend on Postgres features (jsonb, gen_random_uuid, row locks,
// foreign keys). They are skipped unless TEST_DATABASE_URL is set, so a plain
// `go test ./...` (including the one in the Dockerfile) still passes without a
// database. The validation tests in validation_test.go never need one.
//
// To run everything against the docker-compose database:
//
//	docker compose up -d postgres
//	docker exec planning_db createdb -U planning_user planning_test
//	TEST_DATABASE_URL="postgres://planning_user:planning_pass@localhost:5433/planning_test?sslmode=disable" \
//	  go test ./app/internal/handler/ -v
//
// Every test truncates all application tables, so the database name must
// contain "test"; anything else is refused.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"planning-service/app/internal/database"
	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
	"gorm.io/datatypes"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

type obj = map[string]any

var (
	dbOnce   sync.Once
	sharedDB *gorm.DB
	dbErr    error
)

// appTables lists every table the service writes to. Migration bookkeeping and
// seeded presets are left alone.
var appTables = []string{
	"selections", "round_previews", "fact_acceptances", "fact_collection_refs",
	"reopen_operations", "integration_rounds", "confirmed_selections", "invitations",
	"questions", "proposed_activities", "plan_rounds", "plan_members", "plans",
	"sessions", "users",
}

// testDB returns a migrated database with all application tables emptied, or
// skips the test when TEST_DATABASE_URL is not set. Tests using it must not run
// in parallel with each other.
func testDB(t *testing.T) *gorm.DB {
	t.Helper()
	dsn := os.Getenv("TEST_DATABASE_URL")
	if dsn == "" {
		t.Skip("TEST_DATABASE_URL not set; skipping database-backed test")
	}
	dbOnce.Do(func() { sharedDB, dbErr = openTestDB(dsn) })
	if dbErr != nil {
		t.Fatalf("test database: %v", dbErr)
	}
	if err := sharedDB.Exec("TRUNCATE " + strings.Join(appTables, ", ") + " CASCADE").Error; err != nil {
		t.Fatalf("reset tables: %v", err)
	}
	return sharedDB
}

func openTestDB(dsn string) (*gorm.DB, error) {
	db, err := gorm.Open(postgres.Open(dsn), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
	if err != nil {
		return nil, err
	}
	var name string
	if err := db.Raw("SELECT current_database()").Scan(&name).Error; err != nil {
		return nil, err
	}
	if !strings.Contains(strings.ToLower(name), "test") {
		return nil, fmt.Errorf("refusing to use database %q: every test truncates all tables, so the name must contain \"test\"", name)
	}
	if err := database.Migrate(db); err != nil {
		return nil, fmt.Errorf("migrate: %w", err)
	}
	return db, nil
}

// serve calls a handler directly, as the mux would after routing. body may be
// nil (no body), a string (sent as-is) or any value (sent as JSON). pathValues
// are name/value pairs made available through r.PathValue.
func serve(t *testing.T, h http.HandlerFunc, method, target string, body any, pathValues ...string) *httptest.ResponseRecorder {
	t.Helper()
	var reader io.Reader = http.NoBody
	switch b := body.(type) {
	case nil:
	case string:
		reader = strings.NewReader(b)
	default:
		data, err := json.Marshal(b)
		if err != nil {
			t.Fatalf("encode request body: %v", err)
		}
		reader = bytes.NewReader(data)
	}
	req := httptest.NewRequest(method, target, reader)
	for i := 0; i+1 < len(pathValues); i += 2 {
		req.SetPathValue(pathValues[i], pathValues[i+1])
	}
	rec := httptest.NewRecorder()
	h(rec, req)
	return rec
}

func expectStatus(t *testing.T, rec *httptest.ResponseRecorder, want int) {
	t.Helper()
	if rec.Code != want {
		t.Fatalf("status = %d, want %d; body: %s", rec.Code, want, rec.Body.String())
	}
}

// expectError checks the status, the error code, and that exactly one error
// body was written (a handler that forgets to return writes two).
func expectError(t *testing.T, rec *httptest.ResponseRecorder, status int, code string) {
	t.Helper()
	expectStatus(t, rec, status)
	if n := strings.Count(rec.Body.String(), `"code"`); n != 1 {
		t.Fatalf("expected exactly one error body, found %d: %s", n, rec.Body.String())
	}
	var body struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("error body is not JSON: %v; body: %s", err, rec.Body.String())
	}
	if body.Code != code {
		t.Fatalf("error code = %q, want %q; body: %s", body.Code, code, rec.Body.String())
	}
}

func decodeBody[T any](t *testing.T, rec *httptest.ResponseRecorder) T {
	t.Helper()
	var value T
	if err := json.Unmarshal(rec.Body.Bytes(), &value); err != nil {
		t.Fatalf("decode response: %v; body: %s", err, rec.Body.String())
	}
	return value
}

func countRows(t *testing.T, db *gorm.DB, table any, query string, args ...any) int64 {
	t.Helper()
	var n int64
	if err := db.Model(table).Where(query, args...).Count(&n).Error; err != nil {
		t.Fatalf("count rows: %v", err)
	}
	return n
}

// ---- fixtures ----

func createUser(t *testing.T, db *gorm.DB, username string) model.User {
	t.Helper()
	user := model.User{Username: username}
	if err := db.Create(&user).Error; err != nil {
		t.Fatalf("create user: %v", err)
	}
	return user
}

// createPlan goes through the repository so the organiser membership is created
// exactly as POST /v1/plans does it.
func createPlan(t *testing.T, db *gorm.DB, organiser model.User, title string) model.Plan {
	t.Helper()
	plan := model.Plan{Title: title, Category: model.CategoryDining, State: model.PlanStateDraft, CreatedByUserID: organiser.ID}
	if err := repository.NewPlanRepository(db).CreatePlan(t.Context(), &plan, organiser.Username); err != nil {
		t.Fatalf("create plan: %v", err)
	}
	return plan
}

func addMember(t *testing.T, db *gorm.DB, plan model.Plan, user model.User, role model.MemberRole) model.PlanMember {
	t.Helper()
	member := model.PlanMember{PlanID: plan.ID, UserID: user.ID, DisplayName: user.Username, Role: role}
	if err := db.Create(&member).Error; err != nil {
		t.Fatalf("add member: %v", err)
	}
	return member
}

func createRound(t *testing.T, db *gorm.DB, plan model.Plan) model.PlanRound {
	t.Helper()
	round := model.PlanRound{PlanID: plan.ID}
	if err := repository.NewPlanRoundRepository(db).Create(t.Context(), &round); err != nil {
		t.Fatalf("create round: %v", err)
	}
	return round
}

// publishRound records a draft round as published in the given lifecycle state.
func publishRound(t *testing.T, db *gorm.DB, round model.PlanRound, state, rosterPolicy string) {
	t.Helper()
	published := model.PublishedRound{ID: round.ID, PlanID: round.PlanID, State: state, RosterPolicy: rosterPolicy,
		OptionRevision: round.RoundNumber, OptionSnapshotID: uuid.New(), Definition: datatypes.JSON(`{}`),
		Settings: datatypes.JSON(`{}`), PublishOperationID: uuid.New(), FreezeOperationID: uuid.New()}
	if err := db.Create(&published).Error; err != nil {
		t.Fatalf("publish round: %v", err)
	}
}

func futureTime(d time.Duration) time.Time {
	// Postgres stores microseconds; whole seconds keep comparisons exact.
	return time.Now().Add(d).UTC().Truncate(time.Second)
}
