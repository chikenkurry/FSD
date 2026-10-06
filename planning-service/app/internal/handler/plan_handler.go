package handler

import (
	"encoding/json"
	"net/http"
	"time"
	"errors"

	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

// for incoming create request
type CreatePlanRequest struct {
	Title           string     `json:"title"`
	Description     *string    `json:"description,omitempty"`
	OrganiserID     uuid.UUID  `json:"organiser_id"`
	TimeWindowStart *time.Time `json:"time_window_start,omitempty"`
	TimeWindowEnd   *time.Time `json:"time_window_end,omitempty"`
	OrganiserName   string     `json:"organiser_name"`
}

// for responding
type PlanResponse struct {
	ID              uuid.UUID       `json:"id"`
	Title           string          `json:"title"`
	Description     *string         `json:"description,omitempty"`
	Status          model.PlanState `json:"status"`
	CreatedByUserID uuid.UUID       `json:"created_by_user_id"`
	TimeWindowStart *time.Time      `json:"time_window_start,omitempty"`
	TimeWindowEnd   *time.Time      `json:"time_window_end,omitempty"`
	CreatedAt       time.Time       `json:"created_at"`
	UpdatedAt       time.Time       `json:"updated_at"`

	// Relational details (included when loaded)
	MembersCount            int `json:"members_count,omitempty"`
	RoundsCount             int `json:"rounds_count,omitempty"`
	ProposedActivitiesCount int `json:"proposed_activities_count,omitempty"`
}

type UpdatePlanRequest struct {
	Title           *string          `json:"title,omitempty"`
	Description     *string          `json:"description,omitempty"`
	Status          *model.PlanState `json:"status,omitempty"`
	TimeWindowStart *time.Time       `json:"time_window_start,omitempty"`
	TimeWindowEnd   *time.Time       `json:"time_window_end,omitempty"`
}

type PlanHandler struct {
	repo *repository.PlanRepository
}

type JsonResponse struct {
	Status  string `json:"status"`
	Message string `json:"message"`
}

func NewPlanHandler(repo *repository.PlanRepository) *PlanHandler {
	return &PlanHandler{repo: repo}
}

func (h *PlanHandler) GetHealth(w http.ResponseWriter, r *http.Request) {
	result := JsonResponse{Status: "okay", Message: "service be alive"}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

// POST /v1/plans
func (h *PlanHandler) CreatePlan(w http.ResponseWriter, r *http.Request) {
	var req CreatePlanRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON payload")
		return
	}

	if req.Title == "" || req.OrganiserID == uuid.Nil {
		WriteError(w, http.StatusBadRequest, "title and organiser id are required")
		return
	}

	plan := &model.Plan{
		Title:           req.Title,
		Description:     req.Description,
		Status:          model.PlanStateDraft,
		CreatedByUserID: req.OrganiserID,
		TimeWindowStart: req.TimeWindowStart,
		TimeWindowEnd:   req.TimeWindowEnd,
	}

	if err := h.repo.CreatePlan(r.Context(), plan, req.OrganiserName); err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to create plan")
		return
	}

	WriteJSONResponse(w, http.StatusCreated, toPlanResponse(plan))
}

// GET /v1/plans/{id}
func (h *PlanHandler) GetPlanById(w http.ResponseWriter, r *http.Request) {
	// w.Header().Set("Content-Type", "application/json")
	id := r.PathValue("id")
	if id == "" {
		http.Error(w, "Plan id is required", http.StatusBadRequest)
		return
	}

	plan, err := h.repo.GetPlanById(r.Context(), id)

	if err != nil {
		if err.Error() == "plan not found" {
			http.Error(w, "Plan not found", http.StatusNotFound)
			return
		}
		http.Error(w, "Fail to retreieve plan", http.StatusInternalServerError)
		return
	}

	WriteJSONResponse(w, http.StatusOK, plan)
}

// GET /v1/plans/organiser/{id} - List plans for an organiser
func (h *PlanHandler) ListPlansByOrganiser(w http.ResponseWriter, r *http.Request) {
	organiserID := r.PathValue("id")
	if organiserID == "" {
		http.Error(w, "Organiser id is required", http.StatusBadRequest)
		return
	}

	plans, err := h.repo.ListByOrganiser(r.Context(), organiserID, 20, 0)
	if err != nil {
		http.Error(w, "Failed to list plans", http.StatusInternalServerError)
		return
	}
	WriteJSONResponse(w, http.StatusOK, plans)
}

// PATCH /v1/plans/{id} - Update plan details or transition status
func (h *PlanHandler) UpdatePlan(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	planID, err := uuid.Parse(idStr)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	var req UpdatePlanRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON body")
		return
	}

	// Build dynamic updates map
	updates := make(map[string]interface{})
	if req.Title != nil {
		updates["title"] = *req.Title
	}
	if req.Description != nil {
		updates["description"] = req.Description
	}
	if req.Status != nil {
		updates["status"] = *req.Status
	}
	if req.TimeWindowStart != nil {
		updates["time_window_start"] = req.TimeWindowStart
	}
	if req.TimeWindowEnd != nil {
		updates["time_window_end"] = req.TimeWindowEnd
	}

	if len(updates) == 0 {
		WriteError(w, http.StatusBadRequest, "No fields provided to update")
		return
	}

	updatedPlan, err := h.repo.Update(r.Context(), planID, updates)
	if err != nil {
		if errors.Is(err, repository.ErrPlanNotFound) {
			WriteError(w, http.StatusNotFound, "Plan not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to update plan")
		return
	}

	WriteJSONResponse(w, http.StatusOK, toPlanResponse(updatedPlan))
}

// DELETE /v1/plans/{id} - Delete a plan
func (h *PlanHandler) DeletePlan(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	planID, err := uuid.Parse(idStr)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	if err := h.repo.Delete(r.Context(), planID); err != nil {
		if errors.Is(err, repository.ErrPlanNotFound) {
			WriteError(w, http.StatusNotFound, "Plan not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to delete plan")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// helper funcs

func toPlanResponse(p *model.Plan) PlanResponse {
	return PlanResponse{
		ID:              p.ID,
		Title:           p.Title,
		Description:     p.Description,
		Status:          p.Status,
		CreatedByUserID: p.CreatedByUserID,
		TimeWindowStart: p.TimeWindowStart,
		TimeWindowEnd:   p.TimeWindowEnd,
		CreatedAt:       p.CreatedAt,
		UpdatedAt:       p.UpdatedAt,
	}
}
