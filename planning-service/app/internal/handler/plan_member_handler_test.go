package handler

import (
	"net/http"
	"testing"

	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

func TestAddMember(t *testing.T) {
	db := testDB(t)
	h := NewPlanMemberHandler(repository.NewPlanMemberRepository(db))
	ann := createUser(t, db, "ann")
	plan := createPlan(t, db, ann, "Dinner")
	id := plan.ID.String()

	t.Run("defaults the role to MEMBER", func(t *testing.T) {
		bo := createUser(t, db, "bo")
		rec := serve(t, h.AddMember, "POST", "/v1/plans/"+id+"/members", obj{"user_id": bo.ID, "display_name": "Bo"}, "plan_id", id)
		expectStatus(t, rec, http.StatusCreated)
		got := decodeBody[PlanMemberResponse](t, rec)
		if got.ID == uuid.Nil || got.PlanID != plan.ID || got.UserID != bo.ID || got.DisplayName != "Bo" || got.Role != model.MemberRoleMember {
			t.Fatalf("unexpected member: %+v", got)
		}
		if n := countRows(t, db, &model.PlanMember{}, "plan_id = ? AND user_id = ?", plan.ID, bo.ID); n != 1 {
			t.Fatalf("membership not stored")
		}
	})

	t.Run("keeps an explicit role", func(t *testing.T) {
		cy := createUser(t, db, "cy")
		rec := serve(t, h.AddMember, "POST", "/v1/plans/"+id+"/members", obj{"user_id": cy.ID, "display_name": "Cy", "role": "ORGANISER"}, "plan_id", id)
		expectStatus(t, rec, http.StatusCreated)
		if got := decodeBody[PlanMemberResponse](t, rec); got.Role != model.MemberRoleOrganiser {
			t.Fatalf("role = %q, want ORGANISER", got.Role)
		}
	})

	t.Run("an existing member is a conflict", func(t *testing.T) {
		rec := serve(t, h.AddMember, "POST", "/v1/plans/"+id+"/members", obj{"user_id": ann.ID, "display_name": "Ann again"}, "plan_id", id)
		expectError(t, rec, http.StatusConflict, "OPERATION_CONFLICT")
	})

	t.Run("an unknown user is rejected and nothing is stored", func(t *testing.T) {
		ghost := uuid.New()
		rec := serve(t, h.AddMember, "POST", "/v1/plans/"+id+"/members", obj{"user_id": ghost, "display_name": "Ghost"}, "plan_id", id)
		if rec.Code == http.StatusCreated {
			t.Fatalf("member added for a user that does not exist: %s", rec.Body.String())
		}
		if n := countRows(t, db, &model.PlanMember{}, "user_id = ?", ghost); n != 0 {
			t.Fatal("membership stored for an unknown user")
		}
	})
}

func TestListMembers(t *testing.T) {
	db := testDB(t)
	h := NewPlanMemberHandler(repository.NewPlanMemberRepository(db))
	ann, bo := createUser(t, db, "ann"), createUser(t, db, "bo")
	plan := createPlan(t, db, ann, "Dinner")
	addMember(t, db, plan, bo, model.MemberRoleMember)
	createPlan(t, db, bo, "Someone else's plan")

	rec := serve(t, h.ListMembers, "GET", "/v1/plan_members/"+plan.ID.String(), nil, "plan_id", plan.ID.String())
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[struct {
		Data  []PlanMemberResponse `json:"data"`
		Total int                  `json:"total"`
	}](t, rec)
	if got.Total != 2 || len(got.Data) != 2 {
		t.Fatalf("expected 2 members, got %s", rec.Body.String())
	}
	// Ordered by join time, so the organiser (added with the plan) comes first.
	if got.Data[0].UserID != ann.ID || got.Data[0].Role != model.MemberRoleOrganiser || got.Data[1].UserID != bo.ID {
		t.Fatalf("unexpected member order: %+v", got.Data)
	}
}

func TestUpdateMember(t *testing.T) {
	db := testDB(t)
	h := NewPlanMemberHandler(repository.NewPlanMemberRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Dinner")
	member := addMember(t, db, plan, createUser(t, db, "bo"), model.MemberRoleMember)
	id := member.ID.String()

	rec := serve(t, h.UpdateMember, "PATCH", "/v1/members/"+id, obj{"display_name": "Bobby", "role": "ORGANISER"}, "id", id)
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[PlanMemberResponse](t, rec)
	if got.DisplayName != "Bobby" || got.Role != model.MemberRoleOrganiser {
		t.Fatalf("response does not reflect the update: %+v", got)
	}
	var stored model.PlanMember
	db.First(&stored, "id = ?", member.ID)
	if stored.DisplayName != "Bobby" || stored.Role != model.MemberRoleOrganiser {
		t.Fatalf("update not persisted: %+v", stored)
	}

	missing := uuid.NewString()
	rec = serve(t, h.UpdateMember, "PATCH", "/v1/members/"+missing, obj{"display_name": "x"}, "id", missing)
	expectError(t, rec, http.StatusNotFound, "NOT_FOUND")
}

func TestRemoveMember(t *testing.T) {
	db := testDB(t)
	h := NewPlanMemberHandler(repository.NewPlanMemberRepository(db))
	ann := createUser(t, db, "ann")
	plan := createPlan(t, db, ann, "Dinner")
	member := addMember(t, db, plan, createUser(t, db, "bo"), model.MemberRoleMember)

	t.Run("removes a member", func(t *testing.T) {
		id := member.ID.String()
		expectStatus(t, serve(t, h.RemoveMember, "DELETE", "/v1/members/"+id, nil, "id", id), http.StatusNoContent)
		if n := countRows(t, db, &model.PlanMember{}, "id = ?", member.ID); n != 0 {
			t.Fatal("member still exists")
		}
		expectError(t, serve(t, h.RemoveMember, "DELETE", "/v1/members/"+id, nil, "id", id), http.StatusNotFound, "NOT_FOUND")
	})

	t.Run("refuses to remove the organiser", func(t *testing.T) {
		var organiser model.PlanMember
		db.First(&organiser, "plan_id = ? AND user_id = ?", plan.ID, ann.ID)
		id := organiser.ID.String()
		expectError(t, serve(t, h.RemoveMember, "DELETE", "/v1/members/"+id, nil, "id", id), http.StatusConflict, "OPERATION_CONFLICT")
		if n := countRows(t, db, &model.PlanMember{}, "id = ?", organiser.ID); n != 1 {
			t.Fatal("organiser was removed")
		}
	})
}

func TestRemoveMemberByPlanAndUser(t *testing.T) {
	db := testDB(t)
	h := NewPlanMemberHandler(repository.NewPlanMemberRepository(db))
	plan := createPlan(t, db, createUser(t, db, "ann"), "Dinner")
	bo := createUser(t, db, "bo")
	addMember(t, db, plan, bo, model.MemberRoleMember)
	planID, userID := plan.ID.String(), bo.ID.String()

	rec := serve(t, h.RemoveMemberByPlanAndUser, "DELETE", "/v1/plans/"+planID+"/members/"+userID, nil, "plan_id", planID, "user_id", userID)
	expectStatus(t, rec, http.StatusNoContent)
	if n := countRows(t, db, &model.PlanMember{}, "plan_id = ? AND user_id = ?", plan.ID, bo.ID); n != 0 {
		t.Fatal("member still exists")
	}

	rec = serve(t, h.RemoveMemberByPlanAndUser, "DELETE", "/v1/plans/"+planID+"/members/"+userID, nil, "plan_id", planID, "user_id", userID)
	expectError(t, rec, http.StatusNotFound, "NOT_FOUND")
}
