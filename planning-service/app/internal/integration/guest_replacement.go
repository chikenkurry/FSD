package integration

import (
	"github.com/google/uuid"
	"net/http"
	"planning-service/app/internal/database"
	"planning-service/app/internal/model"
)

// Organiser-assisted guest replacement is explicit and plan-scoped. It does not
// recover an identity by name, reveal old answers, or revoke sessions in other plans.
func (h *Handler) ReplaceGuest(w http.ResponseWriter, r *http.Request) {
	planID, _ := r.Context().Value(planKey{}).(uuid.UUID)
	var body struct {
		PreviousUserID    uuid.UUID `json:"previous_user_id"`
		ReplacementUserID uuid.UUID `json:"replacement_user_id"`
	}
	if decode(w, r, &body) != nil || body.PreviousUserID == uuid.Nil || body.ReplacementUserID == uuid.Nil || body.PreviousUserID == body.ReplacementUserID {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	tx := database.ContextDB(r.Context(), h.db)
	var previous model.PlanMember
	if tx.First(&previous, "plan_id = ? AND user_id = ?", planID, body.PreviousUserID).Error != nil {
		fail(w, 404, "NOT_FOUND")
		return
	}
	if previous.Role != model.MemberRoleMember {
		fail(w, 409, "ORGANISER_RECOVERY_REQUIRES_IDENTITY_PROVIDER")
		return
	}
	var user model.User
	if tx.First(&user, "id = ?", body.ReplacementUserID).Error != nil {
		fail(w, 400, "INVALID_REPLACEMENT")
		return
	}
	if err := tx.Model(&previous).Update("user_id", body.ReplacementUserID).Error; err != nil {
		fail(w, 409, "MEMBER_EXISTS")
		return
	}
	previous.UserID = body.ReplacementUserID
	respond(w, 200, previous)
}
