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

// for incoming create request
type CreatePlanRequest struct {
	Title           string             `json:"title"`
	Description     *string            `json:"description,omitempty"`
	Category        model.PlanCategory `json:"plan_category"`
	State           model.PlanState    `json:"plan_state"`
	OrganiserID     uuid.UUID          `json:"organiser_id"`
	TimeWindowStart *time.Time         `json:"time_window_start,omitempty"`
	TimeWindowEnd   *time.Time         `json:"time_window_end,omitempty"`
	OrganiserName   string             `json:"organiser_name"`
}

// for responding
type PlanResponse struct {
	ID              uuid.UUID          `json:"id"`
	Title           string             `json:"title"`
	Description     *string            `json:"description,omitempty"`
	Category        model.PlanCategory `json:"plan_category"`
	State           model.PlanState    `json:"state"`
	CreatedByUserID uuid.UUID          `json:"created_by_user_id"`
	TimeWindowStart *time.Time         `json:"time_window_start,omitempty"`
	TimeWindowEnd   *time.Time         `json:"time_window_end,omitempty"`
	CreatedAt       time.Time          `json:"created_at"`
	UpdatedAt       time.Time          `json:"updated_at"`
	OrganiserName   string             `json:"organiser_name,omitempty"`

	// Relational details (included when loaded)
	MembersCount            int `json:"members_count,omitempty"`
	RoundsCount             int `json:"rounds_count,omitempty"`
	ProposedActivitiesCount int `json:"proposed_activities_count,omitempty"`
}

type UpdatePlanRequest struct {
	Category        *model.PlanCategory `json:"plan_category,omitempty"`
	Title           *string             `json:"title,omitempty"`
	Description     *string             `json:"description,omitempty"`
	State           *model.PlanState    `json:"state,omitempty"`
	TimeWindowStart *time.Time          `json:"time_window_start,omitempty"`
	TimeWindowEnd   *time.Time          `json:"time_window_end,omitempty"`
}

type PlanHandler struct {
	repo *repository.PlanRepository
}

type JsonResponse struct {
	State   string `json:"state"`
	Message string `json:"message"`
}

func NewPlanHandler(repo *repository.PlanRepository) *PlanHandler {
	return &PlanHandler{repo: repo}
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

	if !req.Category.IsValidCategory() {
		WriteError(w, http.StatusBadRequest, "invalid category")
		return
	}

	if !req.State.IsValidState() {
		WriteError(w, http.StatusBadRequest, "invalid state")
		return
	}

	plan := &model.Plan{
		Title:           req.Title,
		Description:     req.Description,
		Category:        req.Category,
		State:           model.PlanStateDraft,
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
		WriteError(w, http.StatusBadRequest, "Plan id is required")
		return
	}

	plan, err := h.repo.GetPlanById(r.Context(), id)

	if err != nil {
		if err.Error() == "plan not found" {
			WriteError(w, http.StatusNotFound, "Plan not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Fail to retreieve plan")
		return
	}

	WriteJSONResponse(w, http.StatusOK, plan)
}

// GET /v1/plans/details/{id}
func (h *PlanHandler) GetByIDWithDetails(w http.ResponseWriter, r *http.Request) {
	id, err := uuid.Parse(r.PathValue("id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	plan, err := h.repo.GetByIDWithDetails(r.Context(), id)

	if err != nil {
		if err.Error() == "plan not found" {
			WriteError(w, http.StatusNotFound, "Plan not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Fail to retreieve plan")
		return
	}

	// The persistence model stores JSONB bytes. Use the existing activity DTO so
	// nested metadata is JSON too, rather than encoding those bytes as base64.
	activities := make([]ProposedActivityResponse, len(plan.ProposedActivities))
	for i := range plan.ProposedActivities {
		activities[i] = toProposedActivityResponse(&plan.ProposedActivities[i])
	}
	WriteJSONResponse(w, http.StatusOK, struct {
		*model.Plan
		Activities []ProposedActivityResponse `json:"proposed_activities"`
	}{plan, activities})
}

// GET /v1/plans/organiser/{id} - List plans for an organiser
func (h *PlanHandler) ListPlansByOrganiser(w http.ResponseWriter, r *http.Request) {
	h.listPlans(w, r, false)
}

func (h *PlanHandler) ListPlansByMember(w http.ResponseWriter, r *http.Request) {
	h.listPlans(w, r, true)
}

func (h *PlanHandler) listPlans(w http.ResponseWriter, r *http.Request, joined bool) {
	organiserID := r.PathValue("id")
	if organiserID == "" {
		WriteError(w, http.StatusBadRequest, "Organiser id is required")
		return
	}

	var plans []model.Plan
	var err error
	if joined {
		plans, err = h.repo.ListByMember(r.Context(), organiserID, 100, 0)
	} else {
		plans, err = h.repo.ListByOrganiser(r.Context(), organiserID, 20, 0)
	}
	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to list plans")
		return
	}
	responses := make([]PlanResponse, len(plans))
	for i, p := range plans {
		responses[i] = PlanResponse{
			ID:              p.ID,
			Title:           p.Title,
			Category:        p.Category,
			MembersCount:    len(p.Members),
			Description:     p.Description,
			State:           p.State,
			CreatedByUserID: p.CreatedByUserID,
			TimeWindowStart: p.TimeWindowStart,
			TimeWindowEnd:   p.TimeWindowEnd,
			CreatedAt:       p.CreatedAt,
			UpdatedAt:       p.UpdatedAt,
			OrganiserName:   p.CreatedBy.Username,
		}
	}
	WriteJSONResponse(w, http.StatusOK, responses)
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
	if req.Category != nil {
		if !req.Category.IsValidCategory() {
			WriteError(w, http.StatusBadRequest, "invalid category")
			return
		}
		updates["category"] = *req.Category
	}
	if req.Title != nil {
		updates["title"] = *req.Title
	}
	if req.Description != nil {
		updates["description"] = req.Description
	}
	if req.State != nil {
		if !req.State.IsValidState() {
			WriteError(w, http.StatusBadRequest, "invalid state")
			return
		}
		updates["state"] = *req.State
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
		State:           p.State,
		CreatedByUserID: p.CreatedByUserID,
		TimeWindowStart: p.TimeWindowStart,
		TimeWindowEnd:   p.TimeWindowEnd,
		CreatedAt:       p.CreatedAt,
		UpdatedAt:       p.UpdatedAt,
	}
}
