package handler

import (
	"errors"
	"net/http"

	"planning-service/app/internal/httpapi"
	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

type CreateUserRequest struct {
	Username string `json:"username" binding:"required"`
	Email    string `json:"email" binding:"required"`
}

type UpdateUserRequest struct {
	Username string `json:"username"`
	Email    string `json:"email"`
}

type UserResponse struct {
	ID       uuid.UUID `json:"id"`
	Username string    `json:"username"`
	Email    string    `json:"email"`
}

type UserDetailResponse struct {
	ID           uuid.UUID `json:"id"`
	Username     string    `json:"username"`
	Email        string    `json:"email"`
	CreatedPlans int       `json:"created_plans_count,omitempty"`
	Memberships  int       `json:"memberships_count,omitempty"`
}

type UserHandler struct {
	repo *repository.UserRepository
}

func NewUserHandler(repo *repository.UserRepository) *UserHandler {
	return &UserHandler{repo: repo}
}

// POST /users - Create user
func (h *UserHandler) CreateUser(w http.ResponseWriter, r *http.Request) {
	var req CreateUserRequest
	if !httpapi.BindJSON(w, r, &req) {
		return
	}

	if req.Username == "" {
		httpapi.StatusError(w, http.StatusBadRequest, "username is required")
		return
	}

	user := &model.User{
		Username: req.Username,
		Email:    req.Email,
	}

	if err := h.repo.Create(r.Context(), user); err != nil {
		if errors.Is(err, repository.ErrUsernameDuplicate) {
			httpapi.StatusError(w, http.StatusConflict, "Username is already taken")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to create user")
		return
	}

	httpapi.JSON(w, http.StatusCreated, UserResponse{
		ID:       user.ID,
		Username: user.Username,
		Email:    user.Email,
	})
}

// GET /v1/users/{id} - Get single user
func (h *UserHandler) GetUserByID(w http.ResponseWriter, r *http.Request) {
	userID, ok := httpapi.PathUUID(w, r, "id", "Invalid UUID format")
	if !ok {
		return
	}

	user, err := h.repo.GetByIDWithRelations(r.Context(), userID)
	if err != nil {
		if errors.Is(err, repository.ErrUserNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "User not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to fetch user")
		return
	}

	httpapi.JSON(w, http.StatusOK, UserDetailResponse{
		ID:           user.ID,
		Username:     user.Username,
		Email:        user.Email,
		CreatedPlans: len(user.CreatedPlans),
		Memberships:  len(user.Memberships),
	})
}




// PUT /users/{id} - Update user
func (h *UserHandler) UpdateUser(w http.ResponseWriter, r *http.Request) {
	userID, ok := httpapi.PathUUID(w, r, "id", "Invalid UUID format")
	if !ok {
		return
	}

	var req UpdateUserRequest
	if !httpapi.BindJSON(w, r, &req) {
		return
	}

	if req.Username == "" {
		httpapi.StatusError(w, http.StatusBadRequest, "username is required")
		return
	}

	user := &model.User{
		ID:       userID,
		Username: req.Username,
		Email:    req.Email,
	}

	if err := h.repo.Update(r.Context(), user); err != nil {
		if errors.Is(err, repository.ErrUserNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "User not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to update user")
		return
	}

	httpapi.JSON(w, http.StatusOK, UserResponse{
		ID:       user.ID,
		Username: user.Username,
		Email:    user.Email,
	})
}

// DELETE /users/{id} - Delete user
func (h *UserHandler) DeleteUser(w http.ResponseWriter, r *http.Request) {
	userID, ok := httpapi.PathUUID(w, r, "id", "Invalid UUID format")
	if !ok {
		return
	}

	if err := h.repo.Delete(r.Context(), userID); err != nil {
		if errors.Is(err, repository.ErrUserNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "User not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to delete user")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}