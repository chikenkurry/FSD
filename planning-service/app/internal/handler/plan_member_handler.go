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

type AddPlanMemberRequest struct {
	UserID      uuid.UUID         `json:"user_id"`
	DisplayName string            `json:"display_name"`
	Role        model.MemberRole `json:"role,omitempty"` // Default: MEMBER
}

type UpdatePlanMemberRequest struct {
	DisplayName *string            `json:"display_name,omitempty"`
	Role        *model.MemberRole `json:"role,omitempty"`
}

type PlanMemberResponse struct {
	ID          uuid.UUID  `json:"id"`
	PlanID      uuid.UUID  `json:"plan_id"`
	UserID      uuid.UUID  `json:"user_id"`
	DisplayName string     `json:"display_name"`
	Role        model.MemberRole     `json:"role"`
	JoinedAt    time.Time `json:"joined_at"`

	// Preloaded user info if needed
	Username string `json:"username,omitempty"`
}

type PlanMemberHandler struct {
	repo *repository.PlanMemberRepository
}

func NewPlanMemberHandler(repo *repository.PlanMemberRepository) *PlanMemberHandler {
	return &PlanMemberHandler{repo: repo}
}

// POST /v1/plans/{plan_id}/members - Add a user to a plan
func (h *PlanMemberHandler) AddMember(w http.ResponseWriter, r *http.Request) {
	planIDStr := r.PathValue("plan_id")
	planID, err := uuid.Parse(planIDStr)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	var req AddPlanMemberRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON body")
		return
	}

	if req.UserID == uuid.Nil {
		WriteError(w, http.StatusBadRequest, "user_id is required")
		return
	}

	if req.DisplayName == "" {
		WriteError(w, http.StatusBadRequest, "display_name is required")
		return
	}

	role := req.Role
	if role == "" {
		role = model.MemberRoleMember
	}

	member := &model.PlanMember{
		PlanID:      planID,
		UserID:      req.UserID,
		DisplayName: req.DisplayName,
		Role:        role,
	}

	if err := h.repo.AddMember(r.Context(), member); err != nil {
		if errors.Is(err, repository.ErrMemberExists) {
			WriteError(w, http.StatusConflict, "User is already a member of this plan")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to add member to plan")
		return
	}

	WriteJSONResponse(w, http.StatusCreated, toMemberResponse(member))
}

// GET /v1/plan_members/{plan_id}
func (h *PlanMemberHandler) ListMembers(w http.ResponseWriter, r *http.Request){
	idString := r.PathValue("plan_id")
	planID, err := uuid.Parse(idString)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	members, err := h.repo.ListByPlanID(r.Context(), planID)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to list plan members")
		return
	}

	responses := make([]PlanMemberResponse, len(members))
	for i, m := range members {
		responses[i] = toMemberResponse(&m)
	}

	WriteJSONResponse(w, http.StatusOK, map[string]interface{}{
		"data":  responses,
		"total": len(responses),
	})
}

// PATCH /v1/members/{id} - Update a member's role or display name
func (h *PlanMemberHandler) UpdateMember(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	memberID, err := uuid.Parse(idStr)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Member UUID format")
		return
	}

	var req UpdatePlanMemberRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON body")
		return
	}

	updates := make(map[string]interface{})
	if req.DisplayName != nil {
		updates["display_name"] = *req.DisplayName
	}
	if req.Role != nil {
		updates["role"] = *req.Role
	}

	if len(updates) == 0 {
		WriteError(w, http.StatusBadRequest, "No fields provided to update")
		return
	}

	updatedMember, err := h.repo.UpdateMember(r.Context(), memberID, updates)
	if err != nil {
		if errors.Is(err, repository.ErrMemberNotFound) {
			WriteError(w, http.StatusNotFound, "Member not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to update member")
		return
	}

	WriteJSONResponse(w, http.StatusOK, toMemberResponse(updatedMember))
}

// DELETE /v1/members/{id} - Remove a member by membership ID
func (h *PlanMemberHandler) RemoveMember(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	memberID, err := uuid.Parse(idStr)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Member UUID format")
		return
	}

	if err := h.repo.RemoveMember(r.Context(), memberID); err != nil {
		if errors.Is(err, repository.ErrMemberNotFound) {
			WriteError(w, http.StatusNotFound, "Member not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to remove member")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// DELETE /v1/plans/{plan_id}/members/{user_id} - Leave or remove a user from a plan directly
func (h *PlanMemberHandler) RemoveMemberByPlanAndUser(w http.ResponseWriter, r *http.Request) {
	planIDStr := r.PathValue("plan_id")
	planID, err := uuid.Parse(planIDStr)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	userIDStr := r.PathValue("user_id")
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid User UUID format")
		return
	}

	if err := h.repo.RemoveMemberByPlanAndUser(r.Context(), planID, userID); err != nil {
		if errors.Is(err, repository.ErrMemberNotFound) {
			WriteError(w, http.StatusNotFound, "Member record not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to remove member from plan")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// Helper mapping function
func toMemberResponse(m *model.PlanMember) PlanMemberResponse {
	res := PlanMemberResponse{
		ID:          m.ID,
		PlanID:      m.PlanID,
		UserID:      m.UserID,
		DisplayName: m.DisplayName,
		Role:        m.Role,
		JoinedAt:    m.JoinedAt,
	}

	// if m.User != nil {
	// 	res.Username = m.User.Username
	// }

	return res
}