package integration

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

type userKey struct{}

func currentUser(r *http.Request) uuid.UUID {
	id, _ := r.Context().Value(userKey{}).(uuid.UUID)
	return id
}
func digest(token string) string {
	hash := sha256.Sum256([]byte(token))
	return hex.EncodeToString(hash[:])
}

func (h *Handler) sessionUser(ctx context.Context, token string) (uuid.UUID, error) {
	var session Session
	err := h.db.WithContext(ctx).Where("token_hash = ? AND expires_at > ?", digest(token), time.Now()).First(&session).Error
	return session.UserID, err
}

func (h *Handler) RegisterUser(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Username string `json:"username"`
	}
	if decode(w, r, &body) != nil || strings.TrimSpace(body.Username) == "" || len(body.Username) > 255 {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	secret := make([]byte, 32)
	if _, err := rand.Read(secret); err != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	token := base64.RawURLEncoding.EncodeToString(secret)
	user := model.User{Username: body.Username}
	err := h.db.WithContext(r.Context()).Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(&user).Error; err != nil {
			return err
		}
		return tx.Create(&Session{TokenHash: digest(token), UserID: user.ID, ExpiresAt: time.Now().Add(30 * 24 * time.Hour)}).Error
	})
	if err != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	respond(w, 201, map[string]any{"id": user.ID, "username": user.Username, "session_token": token})
}

func (h *Handler) Internal(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		got := sha256.Sum256([]byte(r.Header.Get("x-internal-token")))
		expected := sha256.Sum256([]byte(h.token))
		if len(h.token) < 16 || subtle.ConstantTimeCompare(got[:], expected[:]) != 1 {
			fail(w, 401, "UNAUTHENTICATED")
			return
		}
		next(w, r)
	}
}

func (h *Handler) AuthoriseSession(w http.ResponseWriter, r *http.Request) {
	var body struct {
		SessionToken string    `json:"sessionToken"`
		RoundID      uuid.UUID `json:"roundId"`
	}
	if decode(w, r, &body) != nil {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	user, err := h.sessionUser(r.Context(), body.SessionToken)
	if err != nil {
		fail(w, 401, "UNAUTHENTICATED")
		return
	}
	var round Round
	if h.db.First(&round, "id = ?", body.RoundID).Error != nil || !h.member(user, round.PlanID, false) {
		fail(w, 403, "FORBIDDEN")
		return
	}
	var snapshot struct {
		Roster []string `json:"roster"`
	}
	if json.Unmarshal(round.EvaluationSnapshot(), &snapshot) != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	allowed := round.RosterPolicy == "close" && round.State == roundCollecting
	for _, id := range snapshot.Roster {
		if id == user.String() {
			allowed = true
		}
	}
	respond(w, 200, map[string]any{"memberId": user, "planId": round.PlanID, "roundId": round.ID, "canRespond": allowed})
}

func (h *Handler) member(user, plan uuid.UUID, organiser bool) bool {
	query := h.db.Model(&model.PlanMember{}).Where("plan_id = ? AND user_id = ?", plan, user)
	if organiser {
		query = query.Where("role = ?", model.MemberRoleOrganiser)
	}
	var count int64
	return query.Count(&count).Error == nil && count == 1
}

func (h *Handler) RevokeSession(w http.ResponseWriter, r *http.Request) {
	token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if h.db.WithContext(r.Context()).Delete(&Session{}, "token_hash = ? AND user_id = ?", digest(token), currentUser(r)).Error != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	respond(w, 200, map[string]string{"status": "revoked"})
}

func (h *Handler) RotateSession(w http.ResponseWriter, r *http.Request) {
	secret := make([]byte, 32)
	if _, err := rand.Read(secret); err != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	token := base64.RawURLEncoding.EncodeToString(secret)
	old := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	err := h.db.WithContext(r.Context()).Transaction(func(tx *gorm.DB) error {
		deleted := tx.Delete(&Session{}, "token_hash = ? AND user_id = ?", digest(old), currentUser(r))
		if deleted.Error != nil {
			return deleted.Error
		}
		if deleted.RowsAffected != 1 {
			return gorm.ErrRecordNotFound
		}
		return tx.Create(&Session{TokenHash: digest(token), UserID: currentUser(r), ExpiresAt: time.Now().Add(30 * 24 * time.Hour)}).Error
	})
	if err != nil {
		fail(w, 409, "SESSION_CHANGED")
		return
	}
	respond(w, 200, map[string]any{"session_token": token, "user_id": currentUser(r)})
}
