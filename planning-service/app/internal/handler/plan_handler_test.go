package handler

import (
	"encoding/json"
	"net/http"
	"sort"
	"testing"

	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

func TestCreatePlan(t *testing.T) {
	db := testDB(t)
	h := NewPlanHandler(repository.NewPlanRepository(db))
	ann := createUser(t, db, "ann")

	t.Run("creates a draft plan and makes the creator its organiser", func(t *testing.T) {
		rec := serve(t, h.CreatePlan, "POST", "/v1/plans", obj{
			"title": "Friday dinner", "description": "Somewhere central", "plan_category": "DINING",
			"organiser_id": ann.ID, "organiser_name": "Ann",
		})
		expectStatus(t, rec, http.StatusCreated)
		got := decodeBody[PlanResponse](t, rec)
		if got.ID == uuid.Nil || got.Title != "Friday dinner" || got.Category != model.CategoryDining ||
			got.State != model.PlanStateDraft || got.CreatedByUserID != ann.ID || got.Description == nil || *got.Description != "Somewhere central" {
			t.Fatalf("unexpected response: %+v", got)
		}

		var organiser model.PlanMember
		if err := db.First(&organiser, "plan_id = ? AND user_id = ?", got.ID, ann.ID).Error; err != nil {
			t.Fatalf("organiser membership not created: %v", err)
		}
		if organiser.Role != model.MemberRoleOrganiser || organiser.DisplayName != "Ann" {
			t.Fatalf("unexpected organiser membership: %+v", organiser)
		}
	})

	t.Run("accepts an explicit DRAFT state", func(t *testing.T) {
		rec := serve(t, h.CreatePlan, "POST", "/v1/plans", obj{
			"title": "Trip", "plan_category": "TRAVEL", "organiser_id": ann.ID, "organiser_name": "Ann", "plan_state": "DRAFT",
		})
		expectStatus(t, rec, http.StatusCreated)
	})

	t.Run("rolls back when the organiser does not exist", func(t *testing.T) {
		ghost := uuid.New()
		rec := serve(t, h.CreatePlan, "POST", "/v1/plans", obj{
			"title": "Orphan", "plan_category": "GENERAL", "organiser_id": ghost, "organiser_name": "Ghost",
		})
		if rec.Code == http.StatusCreated {
			t.Fatalf("plan created for a user that does not exist: %s", rec.Body.String())
		}
		if n := countRows(t, db, &model.Plan{}, "created_by_user_id = ?", ghost); n != 0 {
			t.Fatalf("expected no plan rows, found %d", n)
		}
	})
}

func TestGetPlanById(t *testing.T) {
	db := testDB(t)
	h := NewPlanHandler(repository.NewPlanRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Friday dinner")

	rec := serve(t, h.GetPlanById, "GET", "/v1/plans/"+plan.ID.String(), nil, "id", plan.ID.String())
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[model.Plan](t, rec)
	if got.ID != plan.ID || got.Title != "Friday dinner" || got.Category != model.CategoryDining {
		t.Fatalf("unexpected plan: %+v", got)
	}

	missing := uuid.NewString()
	rec = serve(t, h.GetPlanById, "GET", "/v1/plans/"+missing, nil, "id", missing)
	expectError(t, rec, http.StatusNotFound, "NOT_FOUND")
}

func TestGetPlanWithDetails(t *testing.T) {
	db := testDB(t)
	h := NewPlanHandler(repository.NewPlanRepository(db))
	ann, bo := createUser(t, db, "ann"), createUser(t, db, "bo")
	plan := createPlan(t, db, ann, "Friday dinner")
	addMember(t, db, plan, bo, model.MemberRoleMember)
	createRound(t, db, plan)
	if err := db.Create(&model.ProposedActivity{PlanID: plan.ID, Title: "Sushi", Metadata: []byte(`{"brief":{"summary":"Omakase"}}`)}).Error; err != nil {
		t.Fatal(err)
	}
	if err := db.Create(&model.Question{PlanID: plan.ID, Title: "When?", Type: model.QuestionTypeMeetingDate, SortOrder: 1}).Error; err != nil {
		t.Fatal(err)
	}

	rec := serve(t, h.GetByIDWithDetails, "GET", "/v1/plans/details/"+plan.ID.String(), nil, "id", plan.ID.String())
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[struct {
		ID                 uuid.UUID          `json:"id"`
		Members            []model.PlanMember `json:"members"`
		Rounds             []model.PlanRound  `json:"rounds"`
		Questions          []model.Question   `json:"questions"`
		ConfirmedSelection json.RawMessage    `json:"confirmed_selection"`
		ProposedActivities []struct {
			Title    string          `json:"title"`
			Metadata json.RawMessage `json:"metadata"`
		} `json:"proposed_activities"`
	}](t, rec)

	if got.ID != plan.ID || len(got.Members) != 2 || len(got.Rounds) != 1 || len(got.Questions) != 1 || len(got.ProposedActivities) != 1 {
		t.Fatalf("details not fully loaded: %s", rec.Body.String())
	}
	// Metadata is stored as JSONB bytes and must come back as a JSON object, not base64.
	var metadata struct {
		Brief struct{ Summary string } `json:"brief"`
	}
	if err := json.Unmarshal(got.ProposedActivities[0].Metadata, &metadata); err != nil || metadata.Brief.Summary != "Omakase" {
		t.Fatalf("activity metadata not returned as JSON: %s", got.ProposedActivities[0].Metadata)
	}
	if got.ConfirmedSelection != nil {
		t.Fatalf("expected no confirmed selection, got %s", got.ConfirmedSelection)
	}

	missing := uuid.NewString()
	rec = serve(t, h.GetByIDWithDetails, "GET", "/v1/plans/details/"+missing, nil, "id", missing)
	expectError(t, rec, http.StatusNotFound, "NOT_FOUND")
}

func TestListPlans(t *testing.T) {
	db := testDB(t)
	h := NewPlanHandler(repository.NewPlanRepository(db))
	ann, bo := createUser(t, db, "ann"), createUser(t, db, "bo")
	first := createPlan(t, db, ann, "First")
	second := createPlan(t, db, ann, "Second")
	bosPlan := createPlan(t, db, bo, "Bo's trip")
	addMember(t, db, bosPlan, ann, model.MemberRoleMember)
	createPlan(t, db, bo, "Bo only")

	t.Run("by organiser", func(t *testing.T) {
		rec := serve(t, h.ListPlansByOrganiser, "GET", "/v1/plans/organiser/"+ann.ID.String(), nil, "id", ann.ID.String())
		expectStatus(t, rec, http.StatusOK)
		got := decodeBody[[]PlanResponse](t, rec)
		if ids := planIDs(got); len(ids) != 2 || !ids[first.ID] || !ids[second.ID] {
			t.Fatalf("expected ann's two plans, got %s", rec.Body.String())
		}
		assertNewestFirst(t, got)
		for _, p := range got {
			if p.Category != model.CategoryDining || p.OrganiserName != "ann" || p.MembersCount != 1 {
				t.Fatalf("list entry missing fields: %+v", p)
			}
		}
	})

	t.Run("by member includes plans organised by others", func(t *testing.T) {
		rec := serve(t, h.ListPlansByMember, "GET", "/v1/plans/member/"+ann.ID.String(), nil, "id", ann.ID.String())
		expectStatus(t, rec, http.StatusOK)
		got := decodeBody[[]PlanResponse](t, rec)
		ids := planIDs(got)
		if len(ids) != 3 || !ids[first.ID] || !ids[second.ID] || !ids[bosPlan.ID] {
			t.Fatalf("expected ann's three plans, got %s", rec.Body.String())
		}
		assertNewestFirst(t, got)
		for _, p := range got {
			if p.ID == bosPlan.ID && (p.OrganiserName != "bo" || p.MembersCount != 2) {
				t.Fatalf("unexpected entry for bo's plan: %+v", p)
			}
		}
	})

	t.Run("user with no plans gets an empty list", func(t *testing.T) {
		nobody := createUser(t, db, "cy")
		rec := serve(t, h.ListPlansByOrganiser, "GET", "/v1/plans/organiser/"+nobody.ID.String(), nil, "id", nobody.ID.String())
		expectStatus(t, rec, http.StatusOK)
		if got := decodeBody[[]PlanResponse](t, rec); len(got) != 0 {
			t.Fatalf("expected no plans, got %d", len(got))
		}
	})
}

func TestUpdatePlan(t *testing.T) {
	db := testDB(t)
	h := NewPlanHandler(repository.NewPlanRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Friday dinner")
	id := plan.ID.String()

	rec := serve(t, h.UpdatePlan, "PATCH", "/v1/plans/"+id, obj{"title": "Saturday trip", "plan_category": "TRAVEL", "description": "Day trip"}, "id", id)
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[PlanResponse](t, rec)
	if got.Title != "Saturday trip" || got.Category != model.CategoryTravel || got.Description == nil || *got.Description != "Day trip" {
		t.Fatalf("response does not reflect the update: %+v", got)
	}

	var stored model.Plan
	if err := db.First(&stored, "id = ?", plan.ID).Error; err != nil {
		t.Fatal(err)
	}
	if stored.Title != "Saturday trip" || stored.Category != model.CategoryTravel || stored.Description == nil || *stored.Description != "Day trip" {
		t.Fatalf("update not persisted: %+v", stored)
	}

	missing := uuid.NewString()
	rec = serve(t, h.UpdatePlan, "PATCH", "/v1/plans/"+missing, obj{"title": "x"}, "id", missing)
	expectError(t, rec, http.StatusNotFound, "NOT_FOUND")
}

func TestDeletePlan(t *testing.T) {
	db := testDB(t)
	h := NewPlanHandler(repository.NewPlanRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Friday dinner")
	addMember(t, db, plan, createUser(t, db, "bo"), model.MemberRoleMember)
	id := plan.ID.String()

	rec := serve(t, h.DeletePlan, "DELETE", "/v1/plans/"+id, nil, "id", id)
	expectStatus(t, rec, http.StatusNoContent)
	if n := countRows(t, db, &model.Plan{}, "id = ?", plan.ID); n != 0 {
		t.Fatal("plan still exists")
	}
	if n := countRows(t, db, &model.PlanMember{}, "plan_id = ?", plan.ID); n != 0 {
		t.Fatalf("memberships should cascade, %d left", n)
	}

	rec = serve(t, h.DeletePlan, "DELETE", "/v1/plans/"+id, nil, "id", id)
	expectError(t, rec, http.StatusNotFound, "NOT_FOUND")
}

func planIDs(plans []PlanResponse) map[uuid.UUID]bool {
	ids := map[uuid.UUID]bool{}
	for _, p := range plans {
		ids[p.ID] = true
	}
	return ids
}

func assertNewestFirst(t *testing.T, plans []PlanResponse) {
	t.Helper()
	if !sort.SliceIsSorted(plans, func(i, j int) bool { return plans[i].CreatedAt.After(plans[j].CreatedAt) }) {
		t.Fatal("plans are not ordered newest first")
	}
}