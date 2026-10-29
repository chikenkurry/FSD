package integration

import (
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"planning-service/app/internal/database"

	"github.com/google/uuid"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

// testDatabase connects to a disposable PostgreSQL database and applies the
// service migrations. Tests skip when PLANNING_TEST_DATABASE_URL is unset.
func testDatabase(t *testing.T) *gorm.DB {
	t.Helper()
	url := os.Getenv("PLANNING_TEST_DATABASE_URL")
	if url == "" {
		t.Skip("set PLANNING_TEST_DATABASE_URL to run PostgreSQL-backed access tests")
	}
	db, err := gorm.Open(postgres.Open(url), &gorm.Config{Logger: logger.Default.LogMode(logger.Silent)})
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	if err := database.Migrate(db); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return db
}

type accessFixture struct {
	t                                    *testing.T
	db                                   *gorm.DB
	handler                              *Handler
	organiserID, memberID, outsiderID    uuid.UUID
	organiser, member, outsider, expired string
	draftPlan, draftRound, draftQuestion uuid.UUID
	frozenPlan, frozenRound              uuid.UUID
}

func (f *accessFixture) exec(sql string, values ...any) {
	f.t.Helper()
	if err := f.db.Exec(sql, values...).Error; err != nil {
		f.t.Fatalf("fixture %q: %v", sql, err)
	}
}

func (f *accessFixture) user(name string, expiresIn time.Duration) (uuid.UUID, string) {
	id, token := uuid.New(), uuid.NewString()
	f.exec("INSERT INTO users (id, username) VALUES (?, ?)", id, name)
	f.exec("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)", digest(token), id, time.Now().Add(expiresIn))
	return id, token
}

// plan creates a plan with the organiser and member and one draft round.
func (f *accessFixture) plan() (plan, round uuid.UUID) {
	plan, round = uuid.New(), uuid.New()
	f.exec("INSERT INTO plans (id, title, category, created_by_user_id) VALUES (?, 'Team dinner', 'FOOD', ?)", plan, f.organiserID)
	f.exec("INSERT INTO plan_members (plan_id, user_id, display_name, role) VALUES (?, ?, 'Org', 'ORGANISER'), (?, ?, 'Mem', 'MEMBER')",
		plan, f.organiserID, plan, f.memberID)
	f.exec("INSERT INTO plan_rounds (id, plan_id, round_number) VALUES (?, ?, 1)", round, plan)
	return plan, round
}

func (f *accessFixture) publish(plan, round uuid.UUID, state, rosterPolicy string) {
	f.exec(`INSERT INTO integration_rounds (id, plan_id, state, option_revision, option_snapshot_id, definition, settings,
		publish_operation_id, freeze_operation_id, roster_policy) VALUES (?, ?, ?, 1, ?, '{}', '{}', ?, ?, ?)`,
		round, plan, state, uuid.New(), uuid.New(), uuid.New(), rosterPolicy)
}

func newAccessFixture(t *testing.T) *accessFixture {
	db := testDatabase(t)
	f := &accessFixture{t: t, db: db, handler: NewHandler(db, "", "", "fixture-internal-token")}
	f.organiserID, f.organiser = f.user("organiser", time.Hour)
	f.memberID, f.member = f.user("member", time.Hour)
	f.outsiderID, f.outsider = f.user("outsider", time.Hour)
	_, f.expired = f.user("expired", -time.Minute)
	f.draftPlan, f.draftRound = f.plan()
	f.draftQuestion = uuid.New()
	f.exec("INSERT INTO questions (id, plan_id, title, type) VALUES (?, ?, 'Budget?', 'number')", f.draftQuestion, f.draftPlan)
	f.frozenPlan, f.frozenRound = f.plan()
	f.publish(f.frozenPlan, f.frozenRound, roundCollecting, "publication")
	return f
}

type guardCase struct {
	name, method, path, token, body string
	wantStatus                      int
	wantCode                        string
}

func (f *accessFixture) run(t *testing.T, cases []guardCase) {
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK) })
			request := httptest.NewRequest(test.method, test.path, strings.NewReader(test.body))
			if test.token != "" {
				request.Header.Set("Authorization", "Bearer "+test.token)
			}
			response := httptest.NewRecorder()
			f.handler.Guard(next).ServeHTTP(response, request)
			if response.Code != test.wantStatus || !strings.Contains(response.Body.String(), test.wantCode) {
				t.Fatalf("%s %s: got %d %s, want %d %s", test.method, test.path, response.Code, strings.TrimSpace(response.Body.String()), test.wantStatus, test.wantCode)
			}
		})
	}
}

func TestGuardSessionsAndPlanMembership(t *testing.T) {
	f := newAccessFixture(t)
	plan, round := f.draftPlan.String(), f.draftRound.String()
	f.run(t, []guardCase{
		{"unknown token", "GET", "/v1/plans/" + plan, uuid.NewString(), "", 401, "UNAUTHENTICATED"},
		{"expired session", "GET", "/v1/plans/" + plan, f.expired, "", 401, "UNAUTHENTICATED"},
		{"outsider reads plan", "GET", "/v1/plans/" + plan, f.outsider, "", 403, "FORBIDDEN"},
		{"member reads plan", "GET", "/v1/plans/" + plan, f.member, "", 200, ""},
		{"organiser reads plan", "GET", "/v1/plans/" + plan, f.organiser, "", 200, ""},
		{"outsider lists members", "GET", "/v1/plan_members/" + plan, f.outsider, "", 403, "FORBIDDEN"},
		{"member lists members", "GET", "/v1/plan_members/" + plan, f.member, "", 200, ""},
		{"member reads published form", "GET", "/v1/rounds/" + round + "/form", f.member, "", 200, ""},
		{"outsider reads published form", "GET", "/v1/rounds/" + round + "/form", f.outsider, "", 403, "FORBIDDEN"},
		{"unknown round", "GET", "/v1/rounds/" + uuid.NewString() + "/form", f.organiser, "", 403, "FORBIDDEN"},
		{"unknown question", "PATCH", "/v1/question/" + uuid.NewString(), f.organiser, `{}`, 403, "FORBIDDEN"},
	})
}

func TestGuardOrganiserOnlyActions(t *testing.T) {
	f := newAccessFixture(t)
	plan, round, question := f.draftPlan.String(), f.draftRound.String(), f.draftQuestion.String()
	questionBody := `{"plan_id":"` + plan + `","title":"Cuisine?"}`
	f.run(t, []guardCase{
		{"member edits plan", "PATCH", "/v1/plans/" + plan, f.member, `{"title":"Mine now"}`, 403, "FORBIDDEN"},
		{"organiser edits plan", "PATCH", "/v1/plans/" + plan, f.organiser, `{"title":"Team lunch"}`, 200, ""},
		{"member closes round", "POST", "/v1/rounds/" + round + "/close", f.member, `{}`, 403, "FORBIDDEN"},
		{"member creates invite", "POST", "/v1/plans/" + plan + "/invites", f.member, `{}`, 403, "FORBIDDEN"},
		{"organiser creates invite", "POST", "/v1/plans/" + plan + "/invites", f.organiser, `{}`, 200, ""},
		{"member reads creator draft", "GET", "/v1/rounds/" + round + "/draft", f.member, "", 403, "FORBIDDEN"},
		{"organiser reads creator draft", "GET", "/v1/rounds/" + round + "/draft", f.organiser, "", 200, ""},
		{"member previews own answers", "POST", "/v1/rounds/" + round + "/preview", f.member, `{}`, 200, ""},
		{"outsider previews answers", "POST", "/v1/rounds/" + round + "/preview", f.outsider, `{}`, 403, "FORBIDDEN"},
		{"organiser edits question", "PATCH", "/v1/question/" + question, f.organiser, `{"title":"Max budget?"}`, 200, ""},
		{"member edits question", "PATCH", "/v1/question/" + question, f.member, `{"title":"Max budget?"}`, 403, "FORBIDDEN"},
		{"outsider edits question", "PATCH", "/v1/question/" + question, f.outsider, `{"title":"Max budget?"}`, 403, "FORBIDDEN"},
		{"organiser adds question", "POST", "/v1/question", f.organiser, questionBody, 200, ""},
		{"member adds question", "POST", "/v1/question", f.member, questionBody, 403, "FORBIDDEN"},
		{"outsider adds question", "POST", "/v1/question", f.outsider, questionBody, 403, "FORBIDDEN"},
		{"question without a plan", "POST", "/v1/question", f.organiser, `{"title":"Orphan?"}`, 403, "FORBIDDEN"},
	})
}

func TestGuardUserRecordsBelongToTheirOwner(t *testing.T) {
	f := newAccessFixture(t)
	f.run(t, []guardCase{
		{"read own record", "GET", "/v1/users/" + f.memberID.String(), f.member, "", 200, ""},
		{"rename own record", "PUT", "/v1/users/" + f.memberID.String(), f.member, `{"username":"Sam"}`, 200, ""},
		{"rename another user", "PUT", "/v1/users/" + f.organiserID.String(), f.member, `{"username":"Sam"}`, 403, "FORBIDDEN"},
		{"list another user's plans", "GET", "/v1/plans/organiser/" + f.organiserID.String(), f.outsider, "", 403, "FORBIDDEN"},
		{"create plan for another user", "POST", "/v1/plans", f.member, `{"organiser_id":"` + f.organiserID.String() + `"}`, 403, "FORBIDDEN"},
	})
}

func TestGuardProtectsPublishedRounds(t *testing.T) {
	f := newAccessFixture(t)
	plan, round := f.frozenPlan.String(), f.frozenRound.String()
	f.run(t, []guardCase{
		{"edit plan after publishing", "PATCH", "/v1/plans/" + plan, f.organiser, `{"title":"Changed"}`, 409, "REOPEN_REQUIRED"},
		{"add member under publication roster", "POST", "/v1/plans/" + plan + "/members", f.organiser, `{}`, 409, "REOPEN_REQUIRED"},
		{"delete published round", "DELETE", "/v1/rounds/" + round, f.organiser, "", 409, "FROZEN_HISTORY"},
		{"delete plan after publishing", "DELETE", "/v1/plans/" + plan, f.organiser, "", 409, "REOPEN_REQUIRED"},
		{"start another round while collecting", "POST", "/v1/rounds/plans/" + plan, f.organiser, `{}`, 409, "CLOSE_ROUND_FIRST"},
		{"invite while collecting", "POST", "/v1/plans/" + plan + "/invites", f.organiser, `{}`, 200, ""},
		{"lifecycle state through PATCH", "PATCH", "/v1/plans/" + plan, f.organiser, `{"state":"CONFIRMED"}`, 409, "USE_ROUND_LIFECYCLE"},
	})

	// A round that admits members until closing allows roster edits while collecting.
	openPlan, openRound := f.plan()
	f.publish(openPlan, openRound, roundCollecting, "close")
	f.run(t, []guardCase{
		{"add member under close roster", "POST", "/v1/plans/" + openPlan.String() + "/members", f.organiser, `{}`, 200, ""},
		{"edit plan under close roster", "PATCH", "/v1/plans/" + openPlan.String(), f.organiser, `{"title":"Changed"}`, 409, "REOPEN_REQUIRED"},
	})
}
