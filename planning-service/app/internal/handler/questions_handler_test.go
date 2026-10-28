package handler

import (
	"encoding/json"
	"net/http"
	"testing"

	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

func TestCreateQuestion(t *testing.T) {
	db := testDB(t)
	h := NewQuestionHandler(repository.NewQuestionRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Friday dinner")

	create := func(body obj) model.Question {
		t.Helper()
		body["plan_id"] = plan.ID
		rec := serve(t, h.Create, "POST", "/v1/question", body)
		expectStatus(t, rec, http.StatusCreated)
		return decodeBody[model.Question](t, rec)
	}

	first := create(obj{"title": "Which cuisine?", "question_type": "CUSTOM_SINGLE_CHOICE", "is_required": true,
		"options": obj{"choices": []string{"Italian", "Japanese"}}})
	second := create(obj{"title": "Any allergies?", "question_type": "CUSTOM_TEXT"})
	pinned := create(obj{"title": "Budget?", "question_type": "BUDGET", "sort_order": 10})

	if first.ID == uuid.Nil || first.PlanID != plan.ID || first.Type != model.QuestionTypeCustomSingleChoice || !first.IsRequired {
		t.Fatalf("unexpected question: %+v", first)
	}
	if first.SortOrder != 1 || second.SortOrder != 2 {
		t.Fatalf("sort order should auto-increment: got %d then %d", first.SortOrder, second.SortOrder)
	}
	if pinned.SortOrder != 10 {
		t.Fatalf("explicit sort order overwritten: %d", pinned.SortOrder)
	}
	var options struct{ Choices []string }
	if err := json.Unmarshal(first.Options, &options); err != nil || len(options.Choices) != 2 {
		t.Fatalf("options not stored as JSON: %s", first.Options)
	}

	if n := countRows(t, db, &model.Question{}, "plan_id = ?", plan.ID); n != 3 {
		t.Fatalf("expected 3 stored questions, found %d", n)
	}
}

func TestListQuestionsByPlan(t *testing.T) {
	db := testDB(t)
	h := NewQuestionHandler(repository.NewQuestionRepository(db))
	ann := createUser(t, db, "ann")
	plan, other := createPlan(t, db, ann, "Dinner"), createPlan(t, db, ann, "Other")
	for _, q := range []model.Question{
		{PlanID: plan.ID, Title: "Third", Type: model.QuestionTypeCustomText, SortOrder: 3},
		{PlanID: plan.ID, Title: "First", Type: model.QuestionTypeCustomText, SortOrder: 1},
		{PlanID: plan.ID, Title: "Second", Type: model.QuestionTypeCustomText, SortOrder: 2},
		{PlanID: other.ID, Title: "Elsewhere", Type: model.QuestionTypeCustomText, SortOrder: 1},
	} {
		if err := db.Create(&q).Error; err != nil {
			t.Fatal(err)
		}
	}

	rec := serve(t, h.GetQuestionByPlanId, "GET", "/v1/plans/question/"+plan.ID.String(), nil, "plan_id", plan.ID.String())
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[[]model.Question](t, rec)
	if len(got) != 3 || got[0].Title != "First" || got[1].Title != "Second" || got[2].Title != "Third" {
		t.Fatalf("expected this plan's questions in sort order, got %s", rec.Body.String())
	}

	empty := createPlan(t, db, ann, "Empty")
	rec = serve(t, h.GetQuestionByPlanId, "GET", "/v1/plans/question/"+empty.ID.String(), nil, "plan_id", empty.ID.String())
	expectStatus(t, rec, http.StatusOK)
	if body := rec.Body.String(); body != "[]\n" {
		t.Fatalf("a plan without questions should return [], got %q", body)
	}
}

func TestUpdateQuestion(t *testing.T) {
	db := testDB(t)
	h := NewQuestionHandler(repository.NewQuestionRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Dinner")
	question := model.Question{PlanID: plan.ID, Title: "Where?", Type: model.QuestionTypeCustomText, SortOrder: 1}
	if err := db.Create(&question).Error; err != nil {
		t.Fatal(err)
	}
	id := question.ID.String()

	rec := serve(t, h.UpdateQuestion, "PATCH", "/v1/question/"+id, obj{
		"title": "Which area?", "question_type": "LOCATION", "is_required": true, "sort_order": 5, "description": "Pick one",
	}, "question_id", id)
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[model.Question](t, rec)
	if got.Title != "Which area?" || got.Type != model.QuestionTypeLocation || !got.IsRequired || got.SortOrder != 5 {
		t.Fatalf("response does not reflect the update: %+v", got)
	}

	var stored model.Question
	db.First(&stored, "id = ?", question.ID)
	if stored.Title != "Which area?" || stored.Type != model.QuestionTypeLocation || !stored.IsRequired ||
		stored.SortOrder != 5 || stored.Description == nil || *stored.Description != "Pick one" {
		t.Fatalf("update not persisted: %+v", stored)
	}

	missing := uuid.NewString()
	rec = serve(t, h.UpdateQuestion, "PATCH", "/v1/question/"+missing, obj{"title": "x"}, "question_id", missing)
	expectError(t, rec, http.StatusNotFound, "NOT_FOUND")
}

func TestDeleteQuestion(t *testing.T) {
	db := testDB(t)
	h := NewQuestionHandler(repository.NewQuestionRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Dinner")
	question := model.Question{PlanID: plan.ID, Title: "Where?", Type: model.QuestionTypeCustomText}
	if err := db.Create(&question).Error; err != nil {
		t.Fatal(err)
	}
	id := question.ID.String()

	rec := serve(t, h.Delete, "DELETE", "/v1/question/"+id, nil, "question_id", id)
	expectStatus(t, rec, http.StatusNoContent)
	if n := countRows(t, db, &model.Question{}, "id = ?", question.ID); n != 0 {
		t.Fatal("question still exists")
	}

	rec = serve(t, h.Delete, "DELETE", "/v1/question/"+id, nil, "question_id", id)
	expectError(t, rec, http.StatusNotFound, "NOT_FOUND")
}