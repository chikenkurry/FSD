package integration

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func pathParts(path string) []string { return strings.Split(strings.Trim(path, "/"), "/") }

// These paths resolve without a database lookup, so a Handler without a
// database must answer them. Paths that need a row lookup are covered by the
// PostgreSQL-backed tests in access_guard_postgres_test.go.
func TestPlanForPathResolvesPlansFromThePath(t *testing.T) {
	self, other, plan := uuid.New(), uuid.New(), uuid.New()
	cases := []struct {
		name     string
		path     string
		wantPlan uuid.UUID
		wantOK   bool
	}{
		{"session commands need no plan", "/v1/session/revoke", uuid.Nil, true},
		{"user collection needs no plan", "/v1/users", uuid.Nil, true},
		{"own user record", "/v1/users/" + self.String(), uuid.Nil, true},
		{"another user's record", "/v1/users/" + other.String(), uuid.Nil, false},
		{"malformed user ID", "/v1/users/not-a-uuid", uuid.Nil, false},
		{"invitation tokens need no plan", "/v1/invites/abc123/join", uuid.Nil, true},
		{"plan creation needs no plan", "/v1/plans", uuid.Nil, true},
		{"own organised plans", "/v1/plans/organiser/" + self.String(), uuid.Nil, true},
		{"another user's organised plans", "/v1/plans/organiser/" + other.String(), uuid.Nil, false},
		{"own memberships", "/v1/plans/member/" + self.String(), uuid.Nil, true},
		{"another user's memberships", "/v1/plans/member/" + other.String(), uuid.Nil, false},
		{"plan by ID", "/v1/plans/" + plan.String(), plan, true},
		{"plan invitations", "/v1/plans/" + plan.String() + "/invites", plan, true},
		{"plan member removal", "/v1/plans/" + plan.String() + "/members/" + other.String(), plan, true},
		{"plan details", "/v1/plans/details/" + plan.String(), plan, true},
		{"plan questions", "/v1/plans/question/" + plan.String(), plan, true},
		{"malformed plan details ID", "/v1/plans/details/not-a-uuid", uuid.Nil, false},
		{"plan member list", "/v1/plan_members/" + plan.String(), plan, true},
		{"activities for a plan", "/v1/proposed_activity/plans/" + plan.String(), plan, true},
		{"rounds for a plan", "/v1/rounds/plans/" + plan.String(), plan, true},
		{"confirmed selection for a plan", "/v1/confirmed-selection/plans/" + plan.String(), plan, true},
		{"question creation carries its plan in the body", "/v1/question", uuid.Nil, false},
		{"malformed round ID", "/v1/rounds/not-a-uuid/form", uuid.Nil, false},
		{"round opening without an ID", "/v1/rounds/open", uuid.Nil, false},
		{"malformed round to open", "/v1/rounds/open/not-a-uuid", uuid.Nil, false},
		{"unknown resource", "/v1/selections/" + plan.String(), uuid.Nil, false},
		{"version prefix only", "/v1", uuid.Nil, false},
	}
	handler := &Handler{}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			gotPlan, gotOK := handler.planForPath(pathParts(test.path), self)
			if gotPlan != test.wantPlan || gotOK != test.wantOK {
				t.Fatalf("planForPath(%s) = (%s, %v), want (%s, %v)", test.path, gotPlan, gotOK, test.wantPlan, test.wantOK)
			}
		})
	}
}

func TestEditsDefinitionCoversFrozenPlanContent(t *testing.T) {
	id := uuid.NewString()
	cases := map[string]bool{
		"/v1/question":                        true,
		"/v1/question/" + id:                  true,
		"/v1/proposed_activity/plans/" + id:   true,
		"/v1/proposed_activity/" + id:         true,
		"/v1/members/" + id:                   true,
		"/v1/plans/" + id:                     true,
		"/v1/plans/" + id + "/members":        true,
		"/v1/plans/" + id + "/members/" + id:  true,
		"/v1/plans/" + id + "/invites":        false,
		"/v1/plans/" + id + "/replace-member": false,
		"/v1/rounds/" + id + "/close":         false,
		"/v1/rounds/" + id:                    false,
		"/v1/users/" + id:                     false,
		"/v1/confirmed-selection/plans/" + id: false,
	}
	for path, want := range cases {
		if got := editsDefinition(pathParts(path)); got != want {
			t.Errorf("editsDefinition(%s) = %v, want %v", path, got, want)
		}
	}
}

func TestGuardPassesPublicRoutesWithoutASession(t *testing.T) {
	cases := []struct{ method, path string }{
		{"GET", "/health"},
		{"GET", "/health/ready"},
		{"POST", "/v1/users"},
		// Internal routes are protected by their own token check, not a session.
		{"GET", "/internal/rounds/123/selection"},
	}
	for _, test := range cases {
		t.Run(test.method+" "+test.path, func(t *testing.T) {
			reached := false
			next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { reached = true })
			(&Handler{}).Guard(next).ServeHTTP(httptest.NewRecorder(), httptest.NewRequest(test.method, test.path, nil))
			if !reached {
				t.Fatal("public route was blocked by the session guard")
			}
		})
	}
}

func TestGuardRequiresABearerSession(t *testing.T) {
	cases := []struct{ name, method, path, authorization string }{
		{"no header", "GET", "/v1/plans/" + uuid.NewString(), ""},
		{"basic scheme", "GET", "/v1/plans/" + uuid.NewString(), "Basic dXNlcjpwYXNz"},
		{"lowercase scheme", "GET", "/v1/plans/" + uuid.NewString(), "bearer token"},
		{"user listing is not registration", "GET", "/v1/users", ""},
		{"mutation", "PATCH", "/v1/plans/" + uuid.NewString(), ""},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Fatal("unauthenticated request reached the handler") })
			request := httptest.NewRequest(test.method, test.path, nil)
			if test.authorization != "" {
				request.Header.Set("Authorization", test.authorization)
			}
			response := httptest.NewRecorder()
			(&Handler{}).Guard(next).ServeHTTP(response, request)
			if response.Code != http.StatusUnauthorized || !strings.Contains(response.Body.String(), "UNAUTHENTICATED") {
				t.Fatalf("expected 401 UNAUTHENTICATED, got %d %s", response.Code, response.Body.String())
			}
		})
	}
}
