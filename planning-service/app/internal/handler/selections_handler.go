package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"planning-service/app/internal/httpapi"
	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

type ConfirmedSelectionHandler struct {
	repo *repository.ConfirmedSelectionRepository
}

func NewConfirmedSelectionHandler(repo *repository.ConfirmedSelectionRepository) *ConfirmedSelectionHandler {
	return &ConfirmedSelectionHandler{repo: repo}
}

type CreateConfirmedSelectionRequest struct {
	RecommendationRunID uuid.UUID       `json:"recommendation_run_id"`
	Version             int             `json:"version"`
	SelectedActivityID  *uuid.UUID      `json:"selected_activity_id,omitempty"`
	SelectedStartTime   time.Time       `json:"selected_start_time"`
	SelectedEndTime     time.Time       `json:"selected_end_time"`
	FinalCostPerPerson  float64         `json:"final_cost_per_person"`
	SelectionDetails    json.RawMessage `json:"selection_details,omitempty"`
	ConfirmedByUserID   uuid.UUID       `json:"confirmed_by_user_id"`
}

// POST /v1/confirmed-selection/plans/{plan_id}
func (h *ConfirmedSelectionHandler) CreateConfirmedSelection(w http.ResponseWriter, r *http.Request) {
	planID, ok := httpapi.PathUUID(w, r, "plan_id", "Invalid Plan UUID format")
	if !ok {
		return
	}

	var req CreateConfirmedSelectionRequest
	if !httpapi.BindJSON(w, r, &req) {
		return
	}

	selectionDetails := req.SelectionDetails
	if len(selectionDetails) == 0 {
		selectionDetails = json.RawMessage(`{}`)
	}

	selection := &model.ConfirmedSelection{
		PlanID:              planID,
		RecommendationRunID: req.RecommendationRunID,
		Version:             req.Version,
		SelectedActivityID:  req.SelectedActivityID,
		SelectedStartTime:   req.SelectedStartTime,
		SelectedEndTime:     req.SelectedEndTime,
		FinalCostPerPerson:  req.FinalCostPerPerson,
		SelectionDetails:    selectionDetails,
		ConfirmedByUserID:   req.ConfirmedByUserID,
	}

	if err := h.repo.Create(r.Context(), selection); err != nil {
		if errors.Is(err, repository.ErrConfirmedSelectionExists) {
			httpapi.StatusError(w, http.StatusConflict, "A confirmed selection already exists for this plan")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to create confirmed selection")
		return
	}

	httpapi.JSON(w, http.StatusCreated, selection)
}

// GET /v1/confirmed-selection/plans/{plan_id}
func (h *ConfirmedSelectionHandler) GetConfirmedSelectionByPlan(w http.ResponseWriter, r *http.Request) {
	planID, ok := httpapi.PathUUID(w, r, "plan_id", "Invalid Plan UUID format")
	if !ok {
		return
	}

	selection, err := h.repo.GetByPlanID(r.Context(), planID)
	if errors.Is(err, repository.ErrConfirmedSelectionNotFound) {
		httpapi.StatusError(w, http.StatusNotFound, "Confirmed selection not found")
		return
	}
	if err != nil {
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to get confirmed selection")
		return
	}

	httpapi.JSON(w, http.StatusOK, selection)
}