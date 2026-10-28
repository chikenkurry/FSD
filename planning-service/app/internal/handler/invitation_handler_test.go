package handler

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"regexp"
	"testing"
	"time"

	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"gorm.io/gorm"
)

const testJoinURL = "http://example.test/join"

func TestCreateInvitation(t *testing.T) {
	db := testDB(t)
	h := NewInvitationHandler(repository.NewInvitationRepository(db), testJoinURL)
	ann := createUser(t, db, "ann")
	plan := createPlan(t, db, ann, "Dinner")
	id := plan.ID.String()

	t.Run("defaults to a 72 hour link", func(t *testing.T) {
		before := time.Now()
		rec := serve(t, h.CreateInvitation, "POST", "/v1/plans/"+id+"/invites", obj{"created_by": ann.ID}, "plan_id", id)
		expectStatus(t, rec, http.StatusCreated)
		got := decodeBody[InvitationLinkResponse](t, rec)

		if !regexp.MustCompile(`^[0-9a-f]{32}$`).MatchString(got.Token) {
			t.Fatalf("token should be 32 hex characters, got %q", got.Token)
		}
		if got.ShareURL != testJoinURL+"?token="+got.Token {
			t.Fatalf("unexpected share URL %q", got.ShareURL)
		}
		assertExpiresAround(t, got.ExpiresAt, before.Add(72*time.Hour))

		var stored model.Invitation
		if err := db.First(&stored, "token = ?", got.Token).Error; err != nil {
			t.Fatalf("invitation not stored: %v", err)
		}
		if stored.PlanID != plan.ID || stored.CreatedBy != ann.ID || stored.Status != model.InvitationStatusPending || stored.UseCount != 0 {
			t.Fatalf("unexpected stored invitation: %+v", stored)
		}
	})

	t.Run("honours ttl_hours and max_uses", func(t *testing.T) {
		before := time.Now()
		rec := serve(t, h.CreateInvitation, "POST", "/v1/plans/"+id+"/invites", obj{"created_by": ann.ID, "ttl_hours": 2, "max_uses": 5}, "plan_id", id)
		expectStatus(t, rec, http.StatusCreated)
		got := decodeBody[InvitationLinkResponse](t, rec)
		assertExpiresAround(t, got.ExpiresAt, before.Add(2*time.Hour))
		var stored model.Invitation
		db.First(&stored, "token = ?", got.Token)
		if stored.MaxUses != 5 {
			t.Fatalf("max_uses = %d, want 5", stored.MaxUses)
		}
	})
}

func TestAcceptInvitation(t *testing.T) {
	db := testDB(t)
	repo := repository.NewInvitationRepository(db)
	h := NewInvitationHandler(repo, testJoinURL)
	ann := createUser(t, db, "ann")

	invite := func(t *testing.T, plan model.Plan, maxUses int) model.Invitation {
		t.Helper()
		inv, err := repo.Create(t.Context(), plan.ID, ann.ID, time.Hour, maxUses)
		if err != nil {
			t.Fatal(err)
		}
		return *inv
	}
	accept := func(t *testing.T, token string, user model.User) *httptest.ResponseRecorder {
		t.Helper()
		return serve(t, h.AcceptInvitation, "POST", "/v1/invites/"+token+"/join",
			obj{"user_id": user.ID, "display_name": "Guest " + user.Username}, "token", token)
	}

	t.Run("adds the user as a member and counts the use", func(t *testing.T) {
		plan := createPlan(t, db, ann, "Dinner")
		inv := invite(t, plan, 0)
		bo := createUser(t, db, "bo")

		res := accept(t, inv.Token, bo)
		expectStatus(t, res, http.StatusOK)

		var member model.PlanMember
		if err := db.First(&member, "plan_id = ? AND user_id = ?", plan.ID, bo.ID).Error; err != nil {
			t.Fatalf("membership not created: %v", err)
		}
		if member.Role != model.MemberRoleMember || member.DisplayName != "Guest bo" {
			t.Fatalf("unexpected membership: %+v", member)
		}
		var stored model.Invitation
		db.First(&stored, "id = ?", inv.ID)
		if stored.UseCount != 1 || stored.Status != model.InvitationStatusPending {
			t.Fatalf("unlimited invite should stay pending with one use: %+v", stored)
		}
	})

	t.Run("a single-use link is spent after one join", func(t *testing.T) {
		plan := createPlan(t, db, ann, "Dinner")
		inv := invite(t, plan, 1)
		expectStatus(t, accept(t, inv.Token, createUser(t, db, "cy")), http.StatusOK)

		res := accept(t, inv.Token, createUser(t, db, "di"))
		expectError(t, res, http.StatusGone, "EXPIRED")
		var stored model.Invitation
		db.First(&stored, "id = ?", inv.ID)
		if stored.Status != model.InvitationStatusAccepted || stored.UseCount != 1 {
			t.Fatalf("unexpected invitation after max uses: %+v", stored)
		}
	})

	t.Run("an existing member gets a conflict and the use is not counted", func(t *testing.T) {
		plan := createPlan(t, db, ann, "Dinner")
		inv := invite(t, plan, 0)

		res := accept(t, inv.Token, ann) // ann organises this plan
		expectError(t, res, http.StatusConflict, "OPERATION_CONFLICT")
		var stored model.Invitation
		db.First(&stored, "id = ?", inv.ID)
		if stored.UseCount != 0 {
			t.Fatalf("rejected join was counted: %+v", stored)
		}
	})

	t.Run("unknown token", func(t *testing.T) {
		expectError(t, accept(t, "0123456789abcdef0123456789abcdef", createUser(t, db, "ed")), http.StatusNotFound, "NOT_FOUND")
	})

	t.Run("expired link", func(t *testing.T) {
		plan := createPlan(t, db, ann, "Dinner")
		inv := invite(t, plan, 0)
		db.Model(&model.Invitation{}).Where("id = ?", inv.ID).Update("expires_at", time.Now().Add(-time.Minute))

		expectError(t, accept(t, inv.Token, createUser(t, db, "fay")), http.StatusGone, "EXPIRED")
	})

	t.Run("full roster", func(t *testing.T) {
		plan := createPlan(t, db, ann, "Big party")
		fillRoster(t, db, plan, repository.MaxPlanMembers-1) // plus the organiser = full
		inv := invite(t, plan, 0)
		late := createUser(t, db, "late")

		expectError(t, accept(t, inv.Token, late), http.StatusConflict, "OPERATION_CONFLICT")
		if n := countRows(t, db, &model.PlanMember{}, "plan_id = ?", plan.ID); n != repository.MaxPlanMembers {
			t.Fatalf("roster should stay at %d, found %d", repository.MaxPlanMembers, n)
		}
	})

	t.Run("joining depends on the latest round's lifecycle", func(t *testing.T) {
		cases := []struct {
			state, policy string
			want          int
		}{
			{"COLLECTING", "close", http.StatusOK},
			{"COLLECTING", "publication", http.StatusConflict},
			{"REVIEW", "close", http.StatusConflict},
			{"CONFIRMED", "close", http.StatusConflict},
		}
		for i, tc := range cases {
			t.Run(tc.state+"/"+tc.policy, func(t *testing.T) {
				plan := createPlan(t, db, ann, "Dinner")
				publishRound(t, db, createRound(t, db, plan), tc.state, tc.policy)
				inv := invite(t, plan, 0)
				res := accept(t, inv.Token, createUser(t, db, fmt.Sprintf("guest%d", i)))
				expectStatus(t, res, tc.want)
			})
		}

		t.Run("an unpublished draft round does not block joining", func(t *testing.T) {
			plan := createPlan(t, db, ann, "Dinner")
			createRound(t, db, plan)
			expectStatus(t, accept(t, invite(t, plan, 0).Token, createUser(t, db, "drafty")), http.StatusOK)
		})
	})
}

func fillRoster(t *testing.T, db *gorm.DB, plan model.Plan, n int) {
	t.Helper()
	for i := 0; i < n; i++ {
		addMember(t, db, plan, createUser(t, db, fmt.Sprintf("filler%02d", i)), model.MemberRoleMember)
	}
}

func assertExpiresAround(t *testing.T, got, want time.Time) {
	t.Helper()
	if diff := got.Sub(want); diff < -time.Minute || diff > time.Minute {
		t.Fatalf("expires_at = %v, want about %v", got, want)
	}
}