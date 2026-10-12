package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"

	"planning-service/app/internal/repository"
	"planning-service/app/internal/model"

	"github.com/google/uuid"
)

type CreateUserRequest struct {
	Username string `json:"username" binding:"required"`
}

type UpdateUserRequest struct {
	Username string `json:"username" binding:"required"`
}

type UserResponse struct {
	ID       uuid.UUID `json:"id"`
	Username string    `json:"username"`
}

type UserDetailResponse struct {
	ID           uuid.UUID `json:"id"`
	Username     string    `json:"username"`
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
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON payload")
		return
	}

	if req.Username == "" {
		WriteError(w, http.StatusBadRequest, "username is required")
		return
	}

	user := &model.User{
		Username: req.Username,
	}

	if err := h.repo.Create(r.Context(), user); err != nil {
		if errors.Is(err, repository.ErrUsernameDuplicate) {
			WriteError(w, http.StatusConflict, "Username is already taken")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to create user")
		return
	}

	WriteJSONResponse(w, http.StatusCreated, UserResponse{
		ID:       user.ID,
		Username: user.Username,
	})
}

// GET /users/{id} - Get single user
func (h *UserHandler) GetUserByID(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	userID, err := uuid.Parse(idStr)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid UUID format")
		return
	}

	user, err := h.repo.GetByIDWithRelations(r.Context(), userID)
	if err != nil {
		if errors.Is(err, repository.ErrUserNotFound) {
			WriteError(w, http.StatusNotFound, "User not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to fetch user")
		return
	}

	WriteJSONResponse(w, http.StatusOK, UserDetailResponse{
		ID:           user.ID,
		Username:     user.Username,
		CreatedPlans: len(user.CreatedPlans),
		Memberships:  len(user.Memberships),
	})
}

// GET /users - List users with pagination
func (h *UserHandler) ListUsers(w http.ResponseWriter, r *http.Request) {
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit <= 0 || limit > 100 {
		limit = 20
	}

	offset, _ := strconv.Atoi(r.URL.Query().Get("offset"))
	if offset < 0 {
		offset = 0
	}

	users, total, err := h.repo.List(r.Context(), limit, offset)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to fetch users")
		return
	}

	responseList := make([]UserResponse, len(users))
	for i, u := range users {
		responseList[i] = UserResponse{
			ID:       u.ID,
			Username: u.Username,
		}
	}

	WriteJSONResponse(w, http.StatusOK, map[string]interface{}{
		"data":   responseList,
		"total":  total,
		"limit":  limit,
		"offset": offset,
	})
}

// PUT /users/{id} - Update user
func (h *UserHandler) UpdateUser(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	userID, err := uuid.Parse(idStr)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid UUID format")
		return
	}

	var req UpdateUserRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON payload")
		return
	}

	if req.Username == "" {
		WriteError(w, http.StatusBadRequest, "username is required")
		return
	}

	user := &model.User{
		ID:       userID,
		Username: req.Username,
	}

	if err := h.repo.Update(r.Context(), user); err != nil {
		if errors.Is(err, repository.ErrUserNotFound) {
			WriteError(w, http.StatusNotFound, "User not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to update user")
		return
	}

	WriteJSONResponse(w, http.StatusOK, UserResponse{
		ID:       user.ID,
		Username: user.Username,
	})
}

// DELETE /users/{id} - Delete user
func (h *UserHandler) DeleteUser(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	userID, err := uuid.Parse(idStr)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid UUID format")
		return
	}

	if err := h.repo.Delete(r.Context(), userID); err != nil {
		if errors.Is(err, repository.ErrUserNotFound) {
			WriteError(w, http.StatusNotFound, "User not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to delete user")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}
