package handler

import (
	"encoding/json"
	"net/http"
	"testing"

	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

func TestCreateActivity(t *testing.T) {
	db := testDB(t)
	h := NewProposedActivityHandler(repository.NewProposedActivityRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Dinner")
	id := plan.ID.String()

	t.Run("stores every field", func(t *testing.T) {
		rec := serve(t, h.CreateActivity, "POST", "/v1/proposed_activity/plans/"+id, obj{
			"title": "Sushi bar", "description": "Counter seats", "est_cost_per_person": 42.5, "duration_minutes": 90,
			"metadata": obj{"identity": obj{"place_id": "abc123"}},
		}, "plan_id", id)
		expectStatus(t, rec, http.StatusCreated)
		got := decodeBody[ProposedActivityResponse](t, rec)
		if got.ID == uuid.Nil || got.PlanID != plan.ID || got.Title != "Sushi bar" || got.EstCostPerPerson != 42.5 ||
			got.DurationMinutes != 90 || got.Description == nil || *got.Description != "Counter seats" {
			t.Fatalf("unexpected activity: %+v", got)
		}
		assertJSONEqual(t, got.Metadata, `{"identity":{"place_id":"abc123"}}`)
	})

	t.Run("uses the column defaults for omitted fields", func(t *testing.T) {
		rec := serve(t, h.CreateActivity, "POST", "/v1/proposed_activity/plans/"+id, obj{"title": "Picnic"}, "plan_id", id)
		expectStatus(t, rec, http.StatusCreated)
		got := decodeBody[ProposedActivityResponse](t, rec)

		var stored model.ProposedActivity
		db.First(&stored, "id = ?", got.ID)
		if stored.DurationMinutes != 60 || stored.EstCostPerPerson != 0 {
			t.Fatalf("defaults not applied: %+v", stored)
		}
		assertJSONEqual(t, stored.Metadata, `{}`)
		if got.DurationMinutes != 60 {
			t.Fatalf("response duration = %d, want the stored default 60", got.DurationMinutes)
		}
	})

	t.Run("an unknown plan is rejected and nothing is stored", func(t *testing.T) {
		missing := uuid.New()
		rec := serve(t, h.CreateActivity, "POST", "/v1/proposed_activity/plans/"+missing.String(), obj{"title": "Nowhere"}, "plan_id", missing.String())
		if rec.Code == http.StatusCreated {
			t.Fatalf("activity created for a plan that does not exist: %s", rec.Body.String())
		}
		if n := countRows(t, db, &model.ProposedActivity{}, "plan_id = ?", missing); n != 0 {
			t.Fatal("activity stored for an unknown plan")
		}
	})
}

func TestListActivitiesByPlan(t *testing.T) {
	db := testDB(t)
	h := NewProposedActivityHandler(repository.NewProposedActivityRepository(db))
	ann := createUser(t, db, "ann")
	plan, other := createPlan(t, db, ann, "Dinner"), createPlan(t, db, ann, "Other")
	for _, a := range []model.ProposedActivity{
		{PlanID: plan.ID, Title: "First"}, {PlanID: plan.ID, Title: "Second"}, {PlanID: other.ID, Title: "Elsewhere"},
	} {
		if err := db.Create(&a).Error; err != nil {
			t.Fatal(err)
		}
	}

	rec := serve(t, h.ListActivitiesByPlan, "GET", "/v1/proposed_activity/plans/"+plan.ID.String(), nil, "plan_id", plan.ID.String())
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[struct {
		Data []ProposedActivityResponse `json:"data"`
	}](t, rec)
	if len(got.Data) != 2 || got.Data[0].Title != "First" || got.Data[1].Title != "Second" {
		t.Fatalf("expected this plan's activities oldest first, got %s", rec.Body.String())
	}

	empty := createPlan(t, db, ann, "Empty")
	rec = serve(t, h.ListActivitiesByPlan, "GET", "/v1/proposed_activity/plans/"+empty.ID.String(), nil, "plan_id", empty.ID.String())
	expectStatus(t, rec, http.StatusOK)
	if body := rec.Body.String(); body != `{"data":[]}`+"\n" {
		t.Fatalf("a plan without activities should return an empty list, got %q", body)
	}
}

func TestGetActivityByID(t *testing.T) {
	db := testDB(t)
	h := NewProposedActivityHandler(repository.NewProposedActivityRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Dinner")
	activity := model.ProposedActivity{PlanID: plan.ID, Title: "Sushi", Metadata: []byte(`{"tag":"fish"}`)}
	if err := db.Create(&activity).Error; err != nil {
		t.Fatal(err)
	}

	rec := serve(t, h.GetActivityByID, "GET", "/v1/proposed_activity/"+activity.ID.String(), nil, "id", activity.ID.String())
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[ProposedActivityResponse](t, rec)
	if got.ID != activity.ID || got.Title != "Sushi" {
		t.Fatalf("unexpected activity: %+v", got)
	}
	assertJSONEqual(t, got.Metadata, `{"tag":"fish"}`)

	missing := uuid.NewString()
	expectError(t, serve(t, h.GetActivityByID, "GET", "/v1/proposed_activity/"+missing, nil, "id", missing), http.StatusNotFound, "NOT_FOUND")
}

func TestUpdateActivity(t *testing.T) {
	db := testDB(t)
	h := NewProposedActivityHandler(repository.NewProposedActivityRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Dinner")
	activity := model.ProposedActivity{PlanID: plan.ID, Title: "Sushi", Metadata: []byte(`{"old":true}`)}
	if err := db.Create(&activity).Error; err != nil {
		t.Fatal(err)
	}
	id := activity.ID.String()

	rec := serve(t, h.UpdateActivity, "PATCH", "/v1/proposed_activity/"+id, obj{
		"title": "Ramen", "description": "Late night", "est_cost_per_person": 18, "duration_minutes": 45, "metadata": obj{"new": true},
	}, "id", id)
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[ProposedActivityResponse](t, rec)
	if got.Title != "Ramen" || got.EstCostPerPerson != 18 || got.DurationMinutes != 45 || got.Description == nil || *got.Description != "Late night" {
		t.Fatalf("response does not reflect the update: %+v", got)
	}

	var stored model.ProposedActivity
	db.First(&stored, "id = ?", activity.ID)
	if stored.Title != "Ramen" || stored.EstCostPerPerson != 18 || stored.DurationMinutes != 45 {
		t.Fatalf("update not persisted: %+v", stored)
	}
	assertJSONEqual(t, stored.Metadata, `{"new":true}`)

	missing := uuid.NewString()
	expectError(t, serve(t, h.UpdateActivity, "PATCH", "/v1/proposed_activity/"+missing, obj{"title": "x"}, "id", missing), http.StatusNotFound, "NOT_FOUND")
}

func TestDeleteActivity(t *testing.T) {
	db := testDB(t)
	h := NewProposedActivityHandler(repository.NewProposedActivityRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Dinner")
	activity := model.ProposedActivity{PlanID: plan.ID, Title: "Sushi"}
	if err := db.Create(&activity).Error; err != nil {
		t.Fatal(err)
	}
	id := activity.ID.String()

	expectStatus(t, serve(t, h.DeleteActivity, "DELETE", "/v1/proposed_activity/"+id, nil, "id", id), http.StatusNoContent)
	if n := countRows(t, db, &model.ProposedActivity{}, "id = ?", activity.ID); n != 0 {
		t.Fatal("activity still exists")
	}
	expectError(t, serve(t, h.DeleteActivity, "DELETE", "/v1/proposed_activity/"+id, nil, "id", id), http.StatusNotFound, "NOT_FOUND")
}

func assertJSONEqual(t *testing.T, got []byte, want string) {
	t.Helper()
	var a, b any
	if err := json.Unmarshal(got, &a); err != nil {
		t.Fatalf("not JSON: %q", got)
	}
	if err := json.Unmarshal([]byte(want), &b); err != nil {
		t.Fatalf("bad expectation %q", want)
	}
	ga, _ := json.Marshal(a)
	gb, _ := json.Marshal(b)
	if string(ga) != string(gb) {
		t.Fatalf("JSON = %s, want %s", ga, gb)
	}
}