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

type AddPlanMemberRequest struct {
	UserID      uuid.UUID        `json:"user_id"`
	DisplayName string           `json:"display_name"`
	Role        model.MemberRole `json:"role,omitempty"` // Default: MEMBER
}

type UpdatePlanMemberRequest struct {
	DisplayName *string           `json:"display_name,omitempty"`
	Role        *model.MemberRole `json:"role,omitempty"`
}

type PlanMemberResponse struct {
	ID          uuid.UUID        `json:"id"`
	PlanID      uuid.UUID        `json:"plan_id"`
	UserID      uuid.UUID        `json:"user_id"`
	DisplayName string           `json:"display_name"`
	Role        model.MemberRole `json:"role"`
	JoinedAt    time.Time        `json:"joined_at"`

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
	planID, ok := httpapi.PathUUID(w, r, "plan_id", "Invalid Plan UUID format")
	if !ok {
		return
	}

	var req AddPlanMemberRequest
	if !httpapi.BindJSON(w, r, &req) {
		return
	}

	if req.UserID == uuid.Nil {
		httpapi.StatusError(w, http.StatusBadRequest, "user_id is required")
		return
	}

	if req.DisplayName == "" {
		httpapi.StatusError(w, http.StatusBadRequest, "display_name is required")
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
			httpapi.StatusError(w, http.StatusConflict, "User is already a member of this plan")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to add member to plan")
		return
	}

	httpapi.JSON(w, http.StatusCreated, toMemberResponse(member))
}

// GET /v1/plan_members/{plan_id}
func (h *PlanMemberHandler) ListMembers(w http.ResponseWriter, r *http.Request)  {
	planID, ok := httpapi.PathUUID(w, r, "plan_id", "Invalid Plan UUID format")
	if !ok {
		return
	}

	members, err := h.repo.ListByPlanID(r.Context(), planID)
	if err != nil {
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to list plan members")
		return
	}

	responses := make([]PlanMemberResponse, len(members))
	for i, m := range members {
		responses[i] = toMemberResponse(&m)
	}

	httpapi.JSON(w, http.StatusOK, map[string]interface{}{
		"data":  responses,
		"total": len(responses),
	})
}

// PATCH /v1/members/{id} - Update a member's role or display name
func (h *PlanMemberHandler) UpdateMember(w http.ResponseWriter, r *http.Request) {
	memberID, ok := httpapi.PathUUID(w, r, "id", "Invalid Member UUID format")
	if !ok {
		return
	}

	var req UpdatePlanMemberRequest
	if !httpapi.BindJSON(w, r, &req) {
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
		httpapi.StatusError(w, http.StatusBadRequest, "No fields provided to update")
		return
	}

	updatedMember, err := h.repo.UpdateMember(r.Context(), memberID, updates)
	if err != nil {
		if errors.Is(err, repository.ErrMemberNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "Member not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to update member")
		return
	}

	httpapi.JSON(w, http.StatusOK, toMemberResponse(updatedMember))
}

// DELETE /v1/members/{id} - Remove a member by membership ID
func (h *PlanMemberHandler) RemoveMember(w http.ResponseWriter, r *http.Request) {
	memberID, ok := httpapi.PathUUID(w, r, "id", "Invalid Member UUID format")
	if !ok {
		return
	}

	existing, err := h.repo.GetMemberByID(r.Context(), memberID)
	if err != nil {
		if errors.Is(err, repository.ErrMemberNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "Member not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to remove member")
		return
	}
	if existing.Role == model.MemberRoleOrganiser {
		httpapi.StatusError(w, http.StatusConflict, "Cannot remove the plan organiser")
		return
	}

	if err := h.repo.RemoveMember(r.Context(), memberID); err != nil {
		if errors.Is(err, repository.ErrMemberNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "Member not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to remove member")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// DELETE /v1/plans/{plan_id}/members/{user_id} - Leave or remove a user from a plan directly
func (h *PlanMemberHandler) RemoveMemberByPlanAndUser(w http.ResponseWriter, r *http.Request) {
	planID, ok := httpapi.PathUUID(w, r, "plan_id", "Invalid Plan UUID format")
	if !ok {
		return
	}
	userID, ok := httpapi.PathUUID(w, r, "user_id", "Invalid User UUID format")
	if !ok {
		return
	}

	if err := h.repo.RemoveMemberByPlanAndUser(r.Context(), planID, userID); err != nil {
		if errors.Is(err, repository.ErrMemberNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "Member record not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to remove member from plan")
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
