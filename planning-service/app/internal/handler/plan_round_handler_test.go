package handler

import (
	"net/http"
	"testing"
	"time"

	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

func TestCreateRound(t *testing.T) {
	db := testDB(t)
	h := NewPlanRoundHandler(repository.NewPlanRoundRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Dinner")
	id := plan.ID.String()

	t.Run("numbers rounds sequentially and starts them inactive", func(t *testing.T) {
		deadline := futureTime(48 * time.Hour)
		rec := serve(t, h.CreateRound, "POST", "/v1/rounds/plans/"+id, obj{"deadline_at": deadline}, "plan_id", id)
		expectStatus(t, rec, http.StatusCreated)
		first := decodeBody[model.PlanRound](t, rec)
		if first.ID == uuid.Nil || first.PlanID != plan.ID || first.RoundNumber != 1 || first.IsActive {
			t.Fatalf("unexpected first round: %+v", first)
		}
		if first.DeadlineAt == nil || !first.DeadlineAt.Equal(deadline) {
			t.Fatalf("deadline = %v, want %v", first.DeadlineAt, deadline)
		}

		rec = serve(t, h.CreateRound, "POST", "/v1/rounds/plans/"+id, obj{}, "plan_id", id)
		expectStatus(t, rec, http.StatusCreated)
		if second := decodeBody[model.PlanRound](t, rec); second.RoundNumber != 2 || second.DeadlineAt != nil {
			t.Fatalf("unexpected second round: %+v", second)
		}
	})

	t.Run("refuses a new round while one is collecting", func(t *testing.T) {
		busy := createPlan(t, db, createUser(t, db, "bo"), "Busy")
		publishRound(t, db, createRound(t, db, busy), "COLLECTING", "close")

		rec := serve(t, h.CreateRound, "POST", "/v1/rounds/plans/"+busy.ID.String(), obj{}, "plan_id", busy.ID.String())
		if rec.Code == http.StatusCreated {
			t.Fatalf("round created while another is collecting: %s", rec.Body.String())
		}
		if n := countRows(t, db, &model.PlanRound{}, "plan_id = ?", busy.ID); n != 1 {
			t.Fatalf("expected the plan to keep 1 round, found %d", n)
		}
	})

	t.Run("allows a new round once the previous one is in review", func(t *testing.T) {
		reviewed := createPlan(t, db, createUser(t, db, "cy"), "Reviewed")
		publishRound(t, db, createRound(t, db, reviewed), "REVIEW", "close")

		rec := serve(t, h.CreateRound, "POST", "/v1/rounds/plans/"+reviewed.ID.String(), obj{}, "plan_id", reviewed.ID.String())
		expectStatus(t, rec, http.StatusCreated)
		if got := decodeBody[model.PlanRound](t, rec); got.RoundNumber != 2 {
			t.Fatalf("round number = %d, want 2", got.RoundNumber)
		}
	})

	t.Run("an unknown plan is rejected", func(t *testing.T) {
		missing := uuid.New()
		rec := serve(t, h.CreateRound, "POST", "/v1/rounds/plans/"+missing.String(), obj{}, "plan_id", missing.String())
		if rec.Code == http.StatusCreated {
			t.Fatalf("round created for a plan that does not exist: %s", rec.Body.String())
		}
	})
}

func TestListRoundsByPlan(t *testing.T) {
	db := testDB(t)
	h := NewPlanRoundHandler(repository.NewPlanRoundRepository(db))
	ann := createUser(t, db, "ann")
	plan := createPlan(t, db, ann, "Dinner")
	createRound(t, db, plan)
	createRound(t, db, plan)
	createRound(t, db, createPlan(t, db, ann, "Other"))

	rec := serve(t, h.ListRoundsByPlan, "GET", "/v1/rounds/plans/"+plan.ID.String(), nil, "plan_id", plan.ID.String())
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[struct {
		Data  []model.PlanRound `json:"data"`
		Total int               `json:"total"`
	}](t, rec)
	if got.Total != 2 || len(got.Data) != 2 || got.Data[0].RoundNumber != 1 || got.Data[1].RoundNumber != 2 {
		t.Fatalf("expected rounds 1 and 2 in order, got %s", rec.Body.String())
	}
}

func TestGetRoundByID(t *testing.T) {
	db := testDB(t)
	h := NewPlanRoundHandler(repository.NewPlanRoundRepository(db))
	round := createRound(t, db, createPlan(t, db, createUser(t, db, "ann"), "Dinner"))

	rec := serve(t, h.GetRoundByID, "GET", "/v1/rounds/"+round.ID.String(), nil, "id", round.ID.String())
	expectStatus(t, rec, http.StatusOK)
	if got := decodeBody[model.PlanRound](t, rec); got.ID != round.ID || got.RoundNumber != 1 {
		t.Fatalf("unexpected round: %+v", got)
	}

	missing := uuid.NewString()
	expectError(t, serve(t, h.GetRoundByID, "GET", "/v1/rounds/"+missing, nil, "id", missing), http.StatusNotFound, "NOT_FOUND")
}

func TestUpdateRound(t *testing.T) {
	db := testDB(t)
	h := NewPlanRoundHandler(repository.NewPlanRoundRepository(db))
	round := createRound(t, db, createPlan(t, db, createUser(t, db, "ann"), "Dinner"))
	id := round.ID.String()
	deadline := futureTime(72 * time.Hour)

	rec := serve(t, h.UpdateRound, "PATCH", "/v1/rounds/"+id, obj{"deadline_at": deadline, "is_active": true}, "id", id)
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[model.PlanRound](t, rec)
	if got.DeadlineAt == nil || !got.DeadlineAt.Equal(deadline) || !got.IsActive {
		t.Fatalf("response does not reflect the update: %+v", got)
	}

	var stored model.PlanRound
	db.First(&stored, "id = ?", round.ID)
	if stored.DeadlineAt == nil || !stored.DeadlineAt.Equal(deadline) || !stored.IsActive {
		t.Fatalf("update not persisted: %+v", stored)
	}

	missing := uuid.NewString()
	expectError(t, serve(t, h.UpdateRound, "PATCH", "/v1/rounds/"+missing, obj{"is_active": false}, "id", missing), http.StatusNotFound, "NOT_FOUND")
}

func TestDeleteRound(t *testing.T) {
	db := testDB(t)
	h := NewPlanRoundHandler(repository.NewPlanRoundRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Dinner")

	t.Run("deletes a draft round", func(t *testing.T) {
		round := createRound(t, db, plan)
		id := round.ID.String()
		expectStatus(t, serve(t, h.DeleteRound, "DELETE", "/v1/rounds/"+id, nil, "id", id), http.StatusNoContent)
		if n := countRows(t, db, &model.PlanRound{}, "id = ?", round.ID); n != 0 {
			t.Fatal("round still exists")
		}
		expectError(t, serve(t, h.DeleteRound, "DELETE", "/v1/rounds/"+id, nil, "id", id), http.StatusNotFound, "NOT_FOUND")
	})

	t.Run("never deletes a published round", func(t *testing.T) {
		round := createRound(t, db, plan)
		publishRound(t, db, round, "REVIEW", "close")
		id := round.ID.String()
		rec := serve(t, h.DeleteRound, "DELETE", "/v1/rounds/"+id, nil, "id", id)
		if rec.Code == http.StatusNoContent {
			t.Fatal("published round was deleted")
		}
		if n := countRows(t, db, &model.PlanRound{}, "id = ?", round.ID); n != 1 {
			t.Fatal("published round is gone")
		}
	})
}