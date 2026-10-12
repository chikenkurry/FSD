package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"time"
	"strings"
	"bytes"
	"io"

	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

type PlanRoundHandler struct {
	repo                 *repository.PlanRoundRepository
	planRepo             *repository.PlanRepository
	participationBaseURL string
	internalAPIToken     string
}

func NewPlanRoundHandler(
	repo *repository.PlanRoundRepository,
	planRepo *repository.PlanRepository,
	participationBaseURL string,
	internalAPIToken string,
) *PlanRoundHandler {
	return &PlanRoundHandler{
		repo:                 repo,
		planRepo:             planRepo,
		participationBaseURL: strings.TrimRight(participationBaseURL, "/"),
		internalAPIToken:     internalAPIToken,
	}
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
		IsActive:   false,
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

// POST /v1/rounds/open/{id}
func (h *PlanRoundHandler) OpenRound(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	roundID, err := uuid.Parse(r.PathValue("id"))
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Round UUID format")
		return
	}

	if h.internalAPIToken == "" || h.participationBaseURL == "" {
		WriteError(w, http.StatusServiceUnavailable, "Participation integration is not configured")
		return
	}

	round, err := h.repo.GetByID(ctx, roundID)
	if err != nil {
		if errors.Is(err, repository.ErrPlanRoundNotFound) {
			WriteError(w, http.StatusNotFound, "Plan round not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to retrieve round")
		return
	}

	plan, err := h.planRepo.GetByIDWithDetails(ctx, round.PlanID)
	if err != nil {
		if errors.Is(err, repository.ErrPlanNotFound) {
			WriteError(w, http.StatusNotFound, "Plan not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to retrieve plan")
		return
	}

	if len(plan.ProposedActivities) < 1 || len(plan.ProposedActivities) > 8 {
		WriteError(w, http.StatusBadRequest, "A plan must have between 1 and 8 proposed activities")
		return
	}

	activityIDs := make([]uuid.UUID, 0, len(plan.ProposedActivities))
	for _, activity := range plan.ProposedActivities {
		activityIDs = append(activityIDs, activity.ID)
	}

	// Use the same round ID as the operation ID for safe retries? idk where to get operation id otherwise.
	provisionRequest := struct {
		OperationID    string      `json:"operationId"`
		RoundID        string      `json:"roundId"`
		PlanID         string      `json:"planId"`
		OptionRevision int         `json:"optionRevision"`
		ActivityIDs    []uuid.UUID `json:"activityIds"`
	}{
		OperationID:    round.ID.String(),
		RoundID:        round.ID.String(),
		PlanID:         round.PlanID.String(),
		OptionRevision: 1,
		ActivityIDs:    activityIDs,
	}

	body, err := json.Marshal(provisionRequest)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to prepare provisioning request")
		return
	}

	request, err := http.NewRequestWithContext(ctx, http.MethodPost, h.participationBaseURL+"/internal/rounds/provision", bytes.NewReader(body))
	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to prepare Participation request")
		return
	}

	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("x-internal-token", h.internalAPIToken)

	client := &http.Client{Timeout: 10 * time.Second}
	response, err := client.Do(request)
	if err != nil {
		WriteError(w, http.StatusBadGateway, "Could not reach Participation Service; retry opening this round")
		return
	}
	defer response.Body.Close()

	responseBody, err := io.ReadAll(response.Body)
	if err != nil {
		WriteError(w, http.StatusBadGateway, "Could not read Participation response; retry opening this round")
		return
	}

	if response.StatusCode < 200 || response.StatusCode >= 300 {
		WriteError(w, http.StatusBadGateway, "Participation provisioning failed; the plan was not marked as collecting")
		return
	}

	// Only after provisioning succeeds, update Planning's state.
	if _, err := h.planRepo.Update(ctx, plan.ID, map[string]interface{}{
		"state": model.PlanStateCollecting,
	}); err != nil {
		WriteError(w, http.StatusInternalServerError, "Provisioning succeeded but updating plan state failed; retry opening this round")
		return
	}

	updatedRound, err := h.repo.Update(ctx, round.ID, map[string]interface{}{
		"is_active": true,
	})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Provisioning succeeded but activating the round failed; retry opening this round")
		return
	}
	updatedRound.IsActive = true

	var participationResult json.RawMessage
	if json.Valid(responseBody) {
		participationResult = json.RawMessage(responseBody)
	}

	WriteJSONResponse(w, http.StatusOK, map[string]interface{}{
		"round":         updatedRound,
		"participation": participationResult,
	})
}
