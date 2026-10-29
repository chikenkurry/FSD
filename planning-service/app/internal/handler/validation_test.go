package handler

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

// These tests need no database. Every handler is built on repositories with a
// nil connection, so a request that slips past validation and reaches the
// database panics, and the test reports it instead of crashing the run.
func TestHandlersRejectInvalidInputBeforeTouchingTheDatabase(t *testing.T) {
	plans := NewPlanHandler(repository.NewPlanRepository(nil))
	users := NewUserHandler(repository.NewUserRepository(nil))
	questions := NewQuestionHandler(repository.NewQuestionRepository(nil))
	invites := NewInvitationHandler(repository.NewInvitationRepository(nil), "http://example.test/join")
	members := NewPlanMemberHandler(repository.NewPlanMemberRepository(nil))
	activities := NewProposedActivityHandler(repository.NewProposedActivityRepository(nil))
	rounds := NewPlanRoundHandler(repository.NewPlanRoundRepository(nil))

	id := uuid.NewString()
	organiser := uuid.NewString()
	past := time.Now().Add(-time.Hour).UTC().Format(time.RFC3339)

	cases := []struct {
		name    string
		handler http.HandlerFunc
		method  string
		body    any
		path    []string
	}{
		// plans
		{"create plan: malformed JSON", plans.CreatePlan, "POST", `{"title":`, nil},
		{"create plan: missing title", plans.CreatePlan, "POST", obj{"plan_category": "DINING", "organiser_id": organiser}, nil},
		{"create plan: missing organiser", plans.CreatePlan, "POST", obj{"title": "Dinner", "plan_category": "DINING"}, nil},
		{"create plan: unknown category", plans.CreatePlan, "POST", obj{"title": "Dinner", "plan_category": "PARTY", "organiser_id": organiser}, nil},
		{"create plan: non-draft state", plans.CreatePlan, "POST", obj{"title": "Dinner", "plan_category": "DINING", "organiser_id": organiser, "plan_state": "CONFIRMED"}, nil},
		{"get plan: empty id", plans.GetPlanById, "GET", nil, []string{"id", ""}},
		{"get plan: bad id", plans.GetPlanById, "GET", nil, []string{"id", "nope"}},
		{"plan details: bad id", plans.GetByIDWithDetails, "GET", nil, []string{"id", "nope"}},
		{"list organiser plans: empty id", plans.ListPlansByOrganiser, "GET", nil, []string{"id", ""}},
		{"list organiser plans: bad id", plans.ListPlansByOrganiser, "GET", nil, []string{"id", "nope"}},
		{"list member plans: empty id", plans.ListPlansByMember, "GET", nil, []string{"id", ""}},
		{"list member plans: bad id", plans.ListPlansByMember, "GET", nil, []string{"id", "nope"}},
		{"update plan: bad id", plans.UpdatePlan, "PATCH", obj{"title": "x"}, []string{"id", "nope"}},
		{"update plan: malformed JSON", plans.UpdatePlan, "PATCH", `{`, []string{"id", id}},
		{"update plan: no fields", plans.UpdatePlan, "PATCH", obj{}, []string{"id", id}},
		{"update plan: unknown category", plans.UpdatePlan, "PATCH", obj{"plan_category": "PARTY"}, []string{"id", id}},
		{"update plan: unknown state", plans.UpdatePlan, "PATCH", obj{"state": "DONE"}, []string{"id", id}},
		{"delete plan: bad id", plans.DeletePlan, "DELETE", nil, []string{"id", "nope"}},

		// users
		{"get user: bad id", users.GetUserByID, "GET", nil, []string{"id", "nope"}},
		{"update user: bad id", users.UpdateUser, "PUT", obj{"username": "ann"}, []string{"id", "nope"}},
		{"update user: malformed JSON", users.UpdateUser, "PUT", `{`, []string{"id", id}},
		{"update user: missing username", users.UpdateUser, "PUT", obj{"email": "a@example.test"}, []string{"id", id}},

		// questions
		{"create question: malformed JSON", questions.Create, "POST", `{`, nil},
		{"create question: missing title", questions.Create, "POST", obj{"plan_id": id}, nil},
		{"create question: missing plan", questions.Create, "POST", obj{"title": "Where?"}, nil},
		{"list questions: bad plan id", questions.GetQuestionByPlanId, "GET", nil, []string{"plan_id", "nope"}},
		{"update question: bad id", questions.UpdateQuestion, "PATCH", obj{"title": "x"}, []string{"question_id", "nope"}},
		{"update question: malformed JSON", questions.UpdateQuestion, "PATCH", `{`, []string{"question_id", id}},
		{"update question: no fields", questions.UpdateQuestion, "PATCH", obj{}, []string{"question_id", id}},
		{"delete question: bad id", questions.Delete, "DELETE", nil, []string{"question_id", "nope"}},

		// invitations
		{"create invite: bad plan id", invites.CreateInvitation, "POST", obj{}, []string{"plan_id", "nope"}},
		{"create invite: malformed JSON", invites.CreateInvitation, "POST", `{`, []string{"plan_id", id}},
		{"accept invite: empty token", invites.AcceptInvitation, "POST", obj{}, []string{"token", ""}},
		{"accept invite: malformed JSON", invites.AcceptInvitation, "POST", `{`, []string{"token", "abc"}},

		// plan members
		{"add member: bad plan id", members.AddMember, "POST", obj{"user_id": id, "display_name": "Bo"}, []string{"plan_id", "nope"}},
		{"add member: malformed JSON", members.AddMember, "POST", `{`, []string{"plan_id", id}},
		{"add member: missing user", members.AddMember, "POST", obj{"display_name": "Bo"}, []string{"plan_id", id}},
		{"add member: missing display name", members.AddMember, "POST", obj{"user_id": id}, []string{"plan_id", id}},
		{"list members: bad plan id", members.ListMembers, "GET", nil, []string{"plan_id", "nope"}},
		{"update member: bad id", members.UpdateMember, "PATCH", obj{"display_name": "x"}, []string{"id", "nope"}},
		{"update member: no fields", members.UpdateMember, "PATCH", obj{}, []string{"id", id}},
		{"remove member: bad id", members.RemoveMember, "DELETE", nil, []string{"id", "nope"}},
		{"remove by plan and user: bad plan", members.RemoveMemberByPlanAndUser, "DELETE", nil, []string{"plan_id", "nope", "user_id", id}},
		{"remove by plan and user: bad user", members.RemoveMemberByPlanAndUser, "DELETE", nil, []string{"plan_id", id, "user_id", "nope"}},

		// proposed activities
		{"create activity: bad plan id", activities.CreateActivity, "POST", obj{"title": "Sushi"}, []string{"plan_id", "nope"}},
		{"create activity: malformed JSON", activities.CreateActivity, "POST", `{`, []string{"plan_id", id}},
		{"create activity: missing title", activities.CreateActivity, "POST", obj{}, []string{"plan_id", id}},
		{"list activities: bad plan id", activities.ListActivitiesByPlan, "GET", nil, []string{"plan_id", "nope"}},
		{"get activity: bad id", activities.GetActivityByID, "GET", nil, []string{"id", "nope"}},
		{"update activity: bad id", activities.UpdateActivity, "PATCH", obj{"title": "x"}, []string{"id", "nope"}},
		{"update activity: empty title", activities.UpdateActivity, "PATCH", obj{"title": ""}, []string{"id", id}},
		{"update activity: negative cost", activities.UpdateActivity, "PATCH", obj{"est_cost_per_person": -1}, []string{"id", id}},
		{"update activity: zero duration", activities.UpdateActivity, "PATCH", obj{"duration_minutes": 0}, []string{"id", id}},
		{"update activity: no fields", activities.UpdateActivity, "PATCH", obj{}, []string{"id", id}},
		{"delete activity: bad id", activities.DeleteActivity, "DELETE", nil, []string{"id", "nope"}},

		// rounds
		{"create round: bad plan id", rounds.CreateRound, "POST", obj{}, []string{"plan_id", "nope"}},
		{"create round: malformed JSON", rounds.CreateRound, "POST", `{`, []string{"plan_id", id}},
		{"create round: past deadline", rounds.CreateRound, "POST", obj{"deadline_at": past}, []string{"plan_id", id}},
		{"list rounds: bad plan id", rounds.ListRoundsByPlan, "GET", nil, []string{"plan_id", "nope"}},
		{"get round: bad id", rounds.GetRoundByID, "GET", nil, []string{"id", "nope"}},
		{"update round: bad id", rounds.UpdateRound, "PATCH", obj{"is_active": true}, []string{"id", "nope"}},
		{"update round: past deadline", rounds.UpdateRound, "PATCH", obj{"deadline_at": past}, []string{"id", id}},
		{"update round: no fields", rounds.UpdateRound, "PATCH", obj{}, []string{"id", id}},
		{"delete round: bad id", rounds.DeleteRound, "DELETE", nil, []string{"id", "nope"}},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			rec := serveWithoutDatabase(t, tc.handler, tc.method, tc.body, tc.path...)
			expectError(t, rec, http.StatusBadRequest, "INVALID_INPUT")
		})
	}
}

// serveWithoutDatabase turns a panic from the nil database into a test failure.
func serveWithoutDatabase(t *testing.T, h http.HandlerFunc, method string, body any, path ...string) (rec *httptest.ResponseRecorder) {
	t.Helper()
	defer func() {
		if r := recover(); r != nil {
			t.Fatalf("request reached the database instead of failing validation: %v", fmt.Sprint(r))
		}
	}()
	return serve(t, h, method, "/test", body, path...)
}
