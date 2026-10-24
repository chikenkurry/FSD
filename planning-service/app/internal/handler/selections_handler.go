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
	planID, err := uuid.Parse(r.PathValue("plan_id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	var req CreateConfirmedSelectionRequest

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON body")
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
			WriteError(w, http.StatusConflict, "A confirmed selection already exists for this plan")
			return
		}

		WriteError(w, http.StatusInternalServerError, "Failed to create confirmed selection")
		return
	}

	WriteJSONResponse(w, http.StatusCreated, selection)
}

// GET /v1/confirmed-selection/plans/{plan_id}
func (h *ConfirmedSelectionHandler) GetConfirmedSelectionByPlan(w http.ResponseWriter, r *http.Request) {
	planID, err := uuid.Parse(r.PathValue("plan_id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	selection, err := h.repo.GetByPlanID(r.Context(), planID)

	if errors.Is(err, repository.ErrConfirmedSelectionNotFound) {
		WriteError(w, http.StatusNotFound, "Confirmed selection not found")
		return
	}

	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to get confirmed selection")
		return
	}

	WriteJSONResponse(w, http.StatusOK, selection)
}
