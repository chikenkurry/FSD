package handler

import (
	"errors"
	"net/http"
	"time"

	"planning-service/app/internal/httpapi"
	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

// for incoming create request
type CreatePlanRequest struct {
	Title       string             `json:"title"`
	Description *string            `json:"description,omitempty"`
	Category    model.PlanCategory `json:"plan_category"`
	// Optional. New plans always start in DRAFT; the round lifecycle moves them on.
	State           model.PlanState `json:"plan_state,omitempty"`
	OrganiserID     uuid.UUID       `json:"organiser_id"`
	TimeWindowStart *time.Time      `json:"time_window_start,omitempty"`
	TimeWindowEnd   *time.Time      `json:"time_window_end,omitempty"`
	OrganiserName   string          `json:"organiser_name"`
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
	if !httpapi.BindJSON(w, r, &req) {
		return
	}

	if req.Title == "" || req.OrganiserID == uuid.Nil {
		httpapi.StatusError(w, http.StatusBadRequest, "title and organiser id are required")
		return
	}

	if !req.Category.IsValidCategory() {
		httpapi.StatusError(w, http.StatusBadRequest, "invalid category")
		return
	}

	// The plan is always created as DRAFT, so only accept a state that agrees
	// with that rather than silently discarding a different one.
	if req.State != "" && req.State != model.PlanStateDraft {
		httpapi.StatusError(w, http.StatusBadRequest, "new plans always start in DRAFT")
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
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to create plan")
		return
	}

	httpapi.JSON(w, http.StatusCreated, toPlanResponse(plan))
}

// GET /v1/plans/{id}
func (h *PlanHandler) GetPlanById(w http.ResponseWriter, r *http.Request) {
	id, ok := httpapi.PathUUID(w, r, "id", "Invalid Plan UUID format")
	if !ok {
		return
	}

	plan, err := h.repo.GetPlanById(r.Context(), id)
	if err != nil {
		if errors.Is(err, repository.ErrPlanNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "Plan not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to retrieve plan")
		return
	}

	httpapi.JSON(w, http.StatusOK, plan)
}

// GET /v1/plans/details/{id}
func (h *PlanHandler) GetByIDWithDetails(w http.ResponseWriter, r *http.Request) {
	id, ok := httpapi.PathUUID(w, r, "id", "Invalid Plan UUID format")
	if !ok {
		return
	}

	plan, err := h.repo.GetByIDWithDetails(r.Context(), id)
	if err != nil {
		if errors.Is(err, repository.ErrPlanNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "Plan not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to retrieve plan")
		return
	}

	// The persistence model stores JSONB bytes. Use the existing activity DTO so
	// nested metadata is JSON too, rather than encoding those bytes as base64.
	activities := make([]ProposedActivityResponse, len(plan.ProposedActivities))
	for i := range plan.ProposedActivities {
		activities[i] = toProposedActivityResponse(&plan.ProposedActivities[i])
	}
	httpapi.JSON(w, http.StatusOK, struct {
		*model.Plan
		Activities []ProposedActivityResponse `json:"proposed_activities"`
	}{plan, activities})
}

// GET /v1/plans/organiser/{id} - List plans for an organiser
func (h *PlanHandler) ListPlansByOrganiser(w http.ResponseWriter, r *http.Request) {
	h.listPlans(w, r, false)
}

// GET /v1/plans/member/{id} - List plans a user is a member of
func (h *PlanHandler) ListPlansByMember(w http.ResponseWriter, r *http.Request) {
	h.listPlans(w, r, true)
}

func (h *PlanHandler) listPlans(w http.ResponseWriter, r *http.Request, joined bool) {
	userID, ok := httpapi.PathUUID(w, r, "id", "Invalid User UUID format")
	if !ok {
		return
	}

	var plans []model.Plan
	var err error
	if joined {
		plans, err = h.repo.ListByMember(r.Context(), userID, 100, 0)
	} else {
		plans, err = h.repo.ListByOrganiser(r.Context(), userID, 20, 0)
	}
	if err != nil {
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to list plans")
		return
	}
	responses := make([]PlanResponse, len(plans))
	for i := range plans {
		responses[i] = toPlanResponse(&plans[i])
		responses[i].MembersCount = len(plans[i].Members)
	}
	httpapi.JSON(w, http.StatusOK, responses)
}

// PATCH /v1/plans/{id} - Update plan details or transition status
func (h *PlanHandler) UpdatePlan(w http.ResponseWriter, r *http.Request) {
	planID, ok := httpapi.PathUUID(w, r, "id", "Invalid Plan UUID format")
	if !ok {
		return
	}

	var req UpdatePlanRequest
	if !httpapi.BindJSON(w, r, &req) {
		return
	}

	// Build dynamic updates map
	updates := make(map[string]interface{})
	if req.Category != nil {
		if !req.Category.IsValidCategory() {
			httpapi.StatusError(w, http.StatusBadRequest, "invalid category")
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
			httpapi.StatusError(w, http.StatusBadRequest, "invalid state")
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
		httpapi.StatusError(w, http.StatusBadRequest, "No fields provided to update")
		return
	}

	updatedPlan, err := h.repo.Update(r.Context(), planID, updates)
	if err != nil {
		if errors.Is(err, repository.ErrPlanNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "Plan not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to update plan")
		return
	}

	httpapi.JSON(w, http.StatusOK, toPlanResponse(updatedPlan))
}

// DELETE /v1/plans/{id} - Delete a plan
func (h *PlanHandler) DeletePlan(w http.ResponseWriter, r *http.Request) {
	planID, ok := httpapi.PathUUID(w, r, "id", "Invalid Plan UUID format")
	if !ok {
		return
	}

	if err := h.repo.Delete(r.Context(), planID); err != nil {
		if errors.Is(err, repository.ErrPlanNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "Plan not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to delete plan")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// helper funcs

// toPlanResponse maps every stored plan field. OrganiserName is filled only when
// CreatedBy has been preloaded (the list endpoints); it is omitted otherwise.
func toPlanResponse(p *model.Plan) PlanResponse {
	return PlanResponse{
		ID:              p.ID,
		Title:           p.Title,
		Description:     p.Description,
		Category:        p.Category,
		State:           p.State,
		CreatedByUserID: p.CreatedByUserID,
		TimeWindowStart: p.TimeWindowStart,
		TimeWindowEnd:   p.TimeWindowEnd,
		CreatedAt:       p.CreatedAt,
		UpdatedAt:       p.UpdatedAt,
		OrganiserName:   p.CreatedBy.Username,
	}
}
