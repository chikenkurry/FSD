package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

type PlanRoundHandler struct {
	repo *repository.PlanRoundRepository
}

func NewPlanRoundHandler(repo *repository.PlanRoundRepository) *PlanRoundHandler {
	return &PlanRoundHandler{repo: repo}
}

type CreatePlanRoundRequest struct {
	DeadlineAt *time.Time `json:"deadline_at,omitempty"`
}

type UpdatePlanRoundRequest struct {
	DeadlineAt *time.Time `json:"deadline_at,omitempty"`
	IsActive   *bool      `json:"is_active,omitempty"`
}

// POST /v1/rounds/plans/{plan_id} - Create a round for a plan
func (h *PlanRoundHandler) CreateRound(w http.ResponseWriter, r *http.Request) {
	planID, err := uuid.Parse(r.PathValue("plan_id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	var req CreatePlanRoundRequest

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON body")
		return
	}

	if req.DeadlineAt != nil && req.DeadlineAt.Before(time.Now()) {
		WriteError(w, http.StatusBadRequest, "Deadline cannot be in the past")
		return
	}

	round := &model.PlanRound{
		PlanID:     planID,
		DeadlineAt: req.DeadlineAt,
	}

	if err := h.repo.Create(r.Context(), round); err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to create plan round")
		return
	}

	WriteJSONResponse(w, http.StatusCreated, round)
}

// GET /v1/rounds/plans/{plan_id} - List all rounds for a plan
func (h *PlanRoundHandler) ListRoundsByPlan(w http.ResponseWriter, r *http.Request) {
	planID, err := uuid.Parse(r.PathValue("plan_id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	rounds, err := h.repo.ListByPlanID(r.Context(), planID)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to list plan rounds")
		return
	}

	WriteJSONResponse(w, http.StatusOK, map[string]interface{}{
		"data":  rounds,
		"total": len(rounds),
	})
}

// GET /v1/rounds/{id} - Get a round by ID
func (h *PlanRoundHandler) GetRoundByID(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(r.PathValue("id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Round UUID format")
		return
	}

	round, err := h.repo.GetByID(r.Context(), id)

	if errors.Is(err, repository.ErrPlanRoundNotFound) {
		WriteError(w, http.StatusNotFound, "Plan round not found")
		return
	}

	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to get plan round")
		return
	}

	WriteJSONResponse(w, http.StatusOK, round)
}

// PATCH /v1/rounds/{id} - Update a round
func (h *PlanRoundHandler) UpdateRound(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(r.PathValue("id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Round UUID format")
		return
	}

	var req UpdatePlanRoundRequest

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON body")
		return
	}

	if req.DeadlineAt != nil && req.DeadlineAt.Before(time.Now()) {
		WriteError(w, http.StatusBadRequest, "Deadline cannot be in the past")
		return
	}

	updates := make(map[string]interface{})

	if req.DeadlineAt != nil {
		updates["deadline_at"] = *req.DeadlineAt
	}

	if req.IsActive != nil {
		updates["is_active"] = *req.IsActive
	}

	if len(updates) == 0 {
		WriteError(w, http.StatusBadRequest, "No fields provided to update")
		return
	}

	updatedRound, err := h.repo.Update(r.Context(), id, updates)
	if err != nil {
		if errors.Is(err, repository.ErrPlanRoundNotFound) {
			WriteError(w, http.StatusNotFound, "Plan round not found")
			return
		}

		WriteError(w, http.StatusInternalServerError, "Failed to update plan round")
		return
	}

	WriteJSONResponse(w, http.StatusOK, updatedRound)
}

// DELETE /v1/rounds/{id} - Delete a round
func (h *PlanRoundHandler) DeleteRound(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(r.PathValue("id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Round UUID format")
		return
	}

	if err := h.repo.Delete(r.Context(), id); err != nil {
		if errors.Is(err, repository.ErrPlanRoundNotFound) {
			WriteError(w, http.StatusNotFound, "Plan round not found")
			return
		}

		WriteError(w, http.StatusInternalServerError, "Failed to delete plan round")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}