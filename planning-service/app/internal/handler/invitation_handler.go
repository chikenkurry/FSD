package handler

import (
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"time"

	"planning-service/app/internal/repository"

	"github.com/google/uuid"
)

type CreateInvitationRequest struct {
	PlanID    uuid.UUID `json:"plan_id"`
	CreatedBy uuid.UUID `json:"created_by"`
	TTLHours  int       `json:"ttl_hours,omitempty"` // Hours until expiration (e.g., 72)
	MaxUses   int       `json:"max_uses,omitempty"`  // 0 = unlimited
}

type AcceptInvitationRequest struct {
	UserID      uuid.UUID `json:"user_id"`
	DisplayName string    `json:"display_name"`
}

type InvitationLinkResponse struct {
	Token     string    `json:"token"`
	ShareURL  string    `json:"share_url"`
	ExpiresAt time.Time `json:"expires_at"`
}

type InvitationHandler struct {
	repo    *repository.InvitationRepository
	baseURL string // e.g. "https://app.yourdomain.com/join"
}

func NewInvitationHandler(repo *repository.InvitationRepository, baseURL string) *InvitationHandler {
	return &InvitationHandler{repo: repo, baseURL: baseURL}
}

// POST /v1/plans/{plan_id}/invites - Organiser generates an invite link
func (h *InvitationHandler) CreateInvitation(w http.ResponseWriter, r *http.Request) {
	planIDStr := r.PathValue("plan_id")
	planID, err := uuid.Parse(planIDStr)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}

	var req CreateInvitationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON payload")
		return
	}

	ttlHours := req.TTLHours
	if ttlHours <= 0 {
		ttlHours = 72 // Default to 3 days
	}

	invitation, err := h.repo.Create(r.Context(), planID, req.CreatedBy, time.Duration(ttlHours)*time.Hour, req.MaxUses)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to create invitation link")
		return
	}

	shareURL := fmt.Sprintf("%s?token=%s", h.baseURL, invitation.Token)

	WriteJSONResponse(w, http.StatusCreated, InvitationLinkResponse{
		Token:     invitation.Token,
		ShareURL:  shareURL,
		ExpiresAt: invitation.ExpiresAt,
	})
}

// POST /v1/invites/{token}/join - Member accepts the invite link and joins the plan
func (h *InvitationHandler) AcceptInvitation(w http.ResponseWriter, r *http.Request) {
	token := r.PathValue("token")
	if token == "" {
		WriteError(w, http.StatusBadRequest, "Token is required")
		return
	}

	var req AcceptInvitationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON payload")
		return
	}

	member, err := h.repo.AcceptInvitation(r.Context(), token, req.UserID, req.DisplayName)
	if err != nil {
		switch {
		case errors.Is(err, repository.ErrInvitationNotFound):
			WriteError(w, http.StatusNotFound, "Invitation link not found")
		case errors.Is(err, repository.ErrJoiningClosed):
			WriteError(w, http.StatusConflict, "Joining is closed for this round")
		case errors.Is(err, repository.ErrMemberExists):
			WriteError(w, http.StatusConflict, "User is already a member of this plan")
		case errors.Is(err, repository.ErrRosterFull):
			WriteError(w, http.StatusConflict, "This plan has reached its member limit")
		case errors.Is(err, repository.ErrInvitationExpired), errors.Is(err, repository.ErrInvitationInvalid):
			WriteError(w, http.StatusGone, "Invitation link is expired or invalid")
		default:
			// Database or other unexpected failure: log it, but don't expose it.
			log.Printf("accept_invitation_failed error=%v", err)
			WriteError(w, http.StatusInternalServerError, "Failed to join the plan")
		}
		return
	}

	WriteJSONResponse(w, http.StatusOK, map[string]interface{}{
		"message": "Successfully joined the plan",
		"member":  member,
	})
}