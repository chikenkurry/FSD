package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"strings"
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
	ShareURL  string    `json:"share_url,omitempty"`
	ExpiresAt time.Time `json:"expires_at"`
}

type InvitationHandler struct {
	repo   *repository.InvitationRepository
	appURL string // public frontend origin, e.g. "https://what2do.example.com"
}

func NewInvitationHandler(repo *repository.InvitationRepository, appURL string) *InvitationHandler {
	return &InvitationHandler{repo: repo, appURL: appURL}
}

// invitationLink matches the link the frontend shares: /#round=<id>&invite=<token>.
func invitationLink(appURL string, round uuid.UUID, token string) string {
	params := url.Values{"round": {round.String()}, "invite": {token}}
	return strings.TrimRight(appURL, "/") + "/#" + params.Encode()
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

	// A plan without a round has no form to open yet, so the link is omitted.
	shareURL := ""
	if round, err := h.repo.LatestRoundID(r.Context(), planID); err == nil {
		shareURL = invitationLink(h.appURL, round, invitation.Token)
	}

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
		if errors.Is(err, repository.ErrInvitationNotFound) {
			WriteError(w, http.StatusNotFound, "Invitation link not found")
			return
		}
		if errors.Is(err, repository.ErrJoiningClosed) {
			WriteError(w, http.StatusConflict, "Joining is closed for this round")
			return
		}
		if errors.Is(err, repository.ErrInvitationExpired) || errors.Is(err, repository.ErrInvitationInvalid) {
			WriteError(w, http.StatusGone, "Invitation link is expired or invalid")
			return
		}
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	WriteJSONResponse(w, http.StatusOK, map[string]interface{}{
		"message": "Successfully joined the plan",
		"member":  member,
	})
}
