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

type ProposedActivityHandler struct {
	repo *repository.ProposedActivityRepository
}

func NewProposedActivityHandler(repo *repository.ProposedActivityRepository) *ProposedActivityHandler {
	return &ProposedActivityHandler{repo: repo}
}

type CreateProposedActivityRequest struct {
	Title            string          `json:"title"`
	Description      *string         `json:"description,omitempty"`
	EstCostPerPerson float64         `json:"est_cost_per_person"`
	DurationMinutes  int             `json:"duration_minutes"`
	Metadata         json.RawMessage `json:"metadata,omitempty"`
}

type UpdateProposedActivityRequest struct {
	Title            *string         `json:"title,omitempty"`
	Description      *string         `json:"description,omitempty"`
	EstCostPerPerson *float64        `json:"est_cost_per_person,omitempty"`
	DurationMinutes  *int            `json:"duration_minutes,omitempty"`
	Metadata         json.RawMessage `json:"metadata,omitempty"`
}

type ProposedActivityResponse struct {
	ID               uuid.UUID       `json:"id"`
	PlanID           uuid.UUID       `json:"plan_id"`
	Title            string          `json:"title"`
	Description      *string         `json:"description,omitempty"`
	EstCostPerPerson float64         `json:"est_cost_per_person"`
	DurationMinutes  int             `json:"duration_minutes"`
	Metadata         json.RawMessage `json:"metadata"`
	CreatedAt        time.Time  	 `json:"created_at"`
}

// POST /v1/proposed_activity/plans/{plan_id} - Add activity to a plan
func (h *ProposedActivityHandler) CreateActivity(w http.ResponseWriter, r *http.Request) {
	planID, err := uuid.Parse(r.PathValue("plan_id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	var req CreateProposedActivityRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON body")
		return
	}

	if req.Title == "" {
		WriteError(w, http.StatusBadRequest, "Title is required")
		return
	}

	if req.EstCostPerPerson < 0 {
		WriteError(w, http.StatusBadRequest, "Cost cannot be negative")
		return
	}

	if req.DurationMinutes <= 0 {
		WriteError(w, http.StatusBadRequest, "Duration must be greater than 0")
		return
	}

	metadata := req.Metadata
	if len(metadata) == 0 {
		metadata = json.RawMessage(`{}`)
	}

	activity := &model.ProposedActivity{
		PlanID:           planID,
		Title:            req.Title,
		Description:      req.Description,
		EstCostPerPerson: req.EstCostPerPerson,
		DurationMinutes:  req.DurationMinutes,
		Metadata:         metadata,
	}

	if err := h.repo.Create(r.Context(), activity); err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to create activity")
		return
	}

	WriteJSONResponse(w, http.StatusCreated, activity)
}

// GET /v1/proposed_activity/plans/{plan_id} - List activities for a plan
func (h *ProposedActivityHandler) ListActivitiesByPlan(w http.ResponseWriter, r *http.Request) {
	planID, err := uuid.Parse(r.PathValue("plan_id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	activities, err := h.repo.ListByPlanID(r.Context(), planID)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to list activities")
		return
	}

	WriteJSONResponse(w, http.StatusOK, map[string]interface{}{"data":  activities})
}

// GET /v1/proposed_activity/{id} - Get an activity by ID
func (h *ProposedActivityHandler) GetActivityByID(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(r.PathValue("id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Activity UUID format")
		return
	}

	activity, err := h.repo.GetByID(r.Context(), id)

	if errors.Is(err, repository.ErrProposedActivityNotFound) {
		WriteError(w, http.StatusNotFound, "Activity not found")
		return
	}

	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to get activity")
		return
	}

	WriteJSONResponse(w, http.StatusOK, activity)
}

// PATCH /v1/proposed_activity/{id} - Update an activity
func (h *ProposedActivityHandler) UpdateActivity(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(r.PathValue("id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Activity UUID format")
		return
	}

	var req UpdateProposedActivityRequest

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON body")
		return
	}

	updates := make(map[string]interface{})

	if req.Title != nil {
		if *req.Title == "" {
			WriteError(w, http.StatusBadRequest, "Title cannot be empty")
			return
		}

		updates["title"] = *req.Title
	}

	if req.Description != nil {
		updates["description"] = *req.Description
	}

	if req.EstCostPerPerson != nil {
		if *req.EstCostPerPerson < 0 {
			WriteError(w, http.StatusBadRequest, "Cost cannot be negative")
			return
		}

		updates["est_cost_per_person"] = *req.EstCostPerPerson
	}

	if req.DurationMinutes != nil {
		if *req.DurationMinutes <= 0 {
			WriteError(w, http.StatusBadRequest, "Duration must be greater than 0")
			return
		}

		updates["duration_minutes"] = *req.DurationMinutes
	}

	if req.Metadata != nil {
		updates["metadata"] = req.Metadata
	}

	if len(updates) == 0 {
		WriteError(w, http.StatusBadRequest, "No fields provided to update")
		return
	}

	updatedActivity, err := h.repo.Update(r.Context(), id, updates)
	if err != nil {
		if errors.Is(err, repository.ErrProposedActivityNotFound) {
			WriteError(w, http.StatusNotFound, "Activity not found")
			return
		}

		WriteError(w, http.StatusInternalServerError, "Failed to update activity")
		return
	}

	WriteJSONResponse(w, http.StatusOK, updatedActivity)
}

// DELETE /v1/proposed_activity/{id} - Delete an activity
func (h *ProposedActivityHandler) DeleteActivity(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(r.PathValue("id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Activity UUID format")
		return
	}

	if err := h.repo.Delete(r.Context(), id); err != nil {
		if errors.Is(err, repository.ErrProposedActivityNotFound) {
			WriteError(w, http.StatusNotFound, "Activity not found")
			return
		}

		WriteError(w, http.StatusInternalServerError, "Failed to delete activity")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}
