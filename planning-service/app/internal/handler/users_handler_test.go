package handler

import (
	"net/http"
	"testing"

	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

func TestGetUserByID(t *testing.T) {
	db := testDB(t)
	h := NewUserHandler(repository.NewUserRepository(db))
	ann, bo := createUser(t, db, "ann"), createUser(t, db, "bo")
	createPlan(t, db, ann, "Ann's plan")
	addMember(t, db, createPlan(t, db, bo, "Bo's plan"), ann, model.MemberRoleMember)

	rec := serve(t, h.GetUserByID, "GET", "/v1/users/"+ann.ID.String(), nil, "id", ann.ID.String())
	expectStatus(t, rec, http.StatusOK)
	got := decodeBody[UserDetailResponse](t, rec)
	// One plan created; two memberships (organiser of her own plan, member of Bo's).
	if got.ID != ann.ID || got.Username != "ann" || got.CreatedPlans != 1 || got.Memberships != 2 {
		t.Fatalf("unexpected user detail: %+v", got)
	}

	missing := uuid.NewString()
	rec = serve(t, h.GetUserByID, "GET", "/v1/users/"+missing, nil, "id", missing)
	expectError(t, rec, http.StatusNotFound, "NOT_FOUND")
}

func TestUpdateUser(t *testing.T) {
	db := testDB(t)
	h := NewUserHandler(repository.NewUserRepository(db))
	ann := createUser(t, db, "ann")
	id := ann.ID.String()

	t.Run("updates username and email", func(t *testing.T) {
		rec := serve(t, h.UpdateUser, "PUT", "/v1/users/"+id, obj{"username": "annie", "email": "annie@example.test"}, "id", id)
		expectStatus(t, rec, http.StatusOK)
		got := decodeBody[UserResponse](t, rec)
		if got.ID != ann.ID || got.Username != "annie" || got.Email != "annie@example.test" {
			t.Fatalf("unexpected response: %+v", got)
		}
		var stored model.User
		db.First(&stored, "id = ?", ann.ID)
		if stored.Username != "annie" || stored.Email != "annie@example.test" {
			t.Fatalf("update not persisted: %+v", stored)
		}
	})

	t.Run("an empty email clears it", func(t *testing.T) {
		rec := serve(t, h.UpdateUser, "PUT", "/v1/users/"+id, obj{"username": "annie"}, "id", id)
		expectStatus(t, rec, http.StatusOK)
		var stored model.User
		db.First(&stored, "id = ?", ann.ID)
		if stored.Email != "" {
			t.Fatalf("email not cleared: %q", stored.Email)
		}
	})

	t.Run("an email already in use is rejected and nothing changes", func(t *testing.T) {
		bo := createUser(t, db, "bo")
		serve(t, h.UpdateUser, "PUT", "/v1/users/"+bo.ID.String(), obj{"username": "bo", "email": "shared@example.test"}, "id", bo.ID.String())

		rec := serve(t, h.UpdateUser, "PUT", "/v1/users/"+id, obj{"username": "renamed", "email": "SHARED@example.test"}, "id", id)
		// Currently a 500, because duplicate-key errors are not translated (see
		// gorm.Config.TranslateError). Tighten to 409 once that is enabled.
		if rec.Code == http.StatusOK {
			t.Fatalf("duplicate email accepted: %s", rec.Body.String())
		}
		var stored model.User
		db.First(&stored, "id = ?", ann.ID)
		if stored.Username != "annie" {
			t.Fatalf("failed update still changed the user: %+v", stored)
		}
	})

	t.Run("unknown user", func(t *testing.T) {
		missing := uuid.NewString()
		rec := serve(t, h.UpdateUser, "PUT", "/v1/users/"+missing, obj{"username": "x"}, "id", missing)
		expectError(t, rec, http.StatusNotFound, "NOT_FOUND")
	})
}
