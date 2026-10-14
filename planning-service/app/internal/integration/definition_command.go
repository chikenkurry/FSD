package integration

import (
	"bytes"
	"errors"
	"github.com/google/uuid"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
	"net/http"
	"planning-service/app/internal/database"
	"planning-service/app/internal/model"
	"strings"
)

type planKey struct{}
type commandResponse struct {
	header http.Header
	status int
	body   bytes.Buffer
}

func (r *commandResponse) Header() http.Header { return r.header }
func (r *commandResponse) WriteHeader(code int) {
	if r.status == 0 {
		r.status = code
	}
}
func (r *commandResponse) Write(body []byte) (int, error) {
	if r.status == 0 {
		r.status = 200
	}
	return r.body.Write(body)
}

var errCommandRejected = errors.New("command rejected")

// DefinitionCommand puts the authoritative lifecycle check and all local writes
// in the same transaction as publication. Authentication remains in Guard.
func (h *Handler) DefinitionCommand(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		planID, ok := r.Context().Value(planKey{}).(uuid.UUID)
		if !ok || planID == uuid.Nil {
			fail(w, 403, "FORBIDDEN")
			return
		}
		result := &commandResponse{header: w.Header().Clone()}
		err := h.db.WithContext(r.Context()).Transaction(func(tx *gorm.DB) error {
			var plan model.Plan
			if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&plan, "id = ?", planID).Error; err != nil {
				return err
			}
			var membership int64
			if err := tx.Model(&model.PlanMember{}).Where("plan_id = ? AND user_id = ? AND role = ?", planID, currentUser(r), model.MemberRoleOrganiser).Count(&membership).Error; err != nil {
				return err
			}
			if membership != 1 {
				fail(result, 403, "FORBIDDEN")
				return errCommandRejected
			}
			parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
			if parts[1] == "rounds" {
				var published int64
				if err := tx.Model(&Round{}).Where("id = ?", r.PathValue("id")).Count(&published).Error; err != nil {
					return err
				}
				if published > 0 {
					fail(result, 409, "FROZEN_HISTORY")
					return errCommandRejected
				}
				if r.Method == "DELETE" {
					var evidence int64
					if err := tx.Model(&model.FactCollectionRef{}).Where("round_id = ?", r.PathValue("id")).Count(&evidence).Error; err != nil {
						return err
					}
					var approvals int64
					if err := tx.Model(&model.FactAcceptance{}).Where("target_round_id = ?", r.PathValue("id")).Count(&approvals).Error; err != nil {
						return err
					}
					if evidence+approvals > 0 {
						fail(result, 409, "FROZEN_HISTORY")
						return errCommandRejected
					}
				}
			}
			var latest model.PlanRound
			if err := tx.Where("plan_id = ?", planID).Order("round_number DESC").First(&latest).Error; err == nil {
				var published Round
				if err := tx.First(&published, "id = ?", latest.ID).Error; err == nil {
					rosterEdit := parts[1] == "members" || (parts[1] == "plans" && len(parts) > 3 && (parts[3] == "members" || parts[3] == "replace-member"))
					if !(rosterEdit && published.State == roundCollecting && published.RosterPolicy == "close") {
						fail(result, 409, "REOPEN_REQUIRED")
						return errCommandRejected
					}
				} else if !errors.Is(err, gorm.ErrRecordNotFound) {
					return err
				}
			} else if !errors.Is(err, gorm.ErrRecordNotFound) {
				return err
			}
			if r.Method == "DELETE" && parts[1] == "plans" {
				var history int64
				if err := tx.Model(&Round{}).Where("plan_id = ?", planID).Count(&history).Error; err != nil {
					return err
				}
				if history > 0 {
					fail(result, 409, "FROZEN_HISTORY")
					return errCommandRejected
				}
				var legacy int64
				if err := tx.Model(&model.ConfirmedSelection{}).Where("plan_id = ?", planID).Count(&legacy).Error; err != nil {
					return err
				}
				var evidence int64
				if err := tx.Table("fact_collection_refs f").Joins("JOIN plan_rounds r ON r.id=f.round_id").Where("r.plan_id = ?", planID).Count(&evidence).Error; err != nil {
					return err
				}
				if legacy+evidence > 0 {
					fail(result, 409, "FROZEN_HISTORY")
					return errCommandRejected
				}
			}
			next(result, r.WithContext(database.TransactionContext(r.Context(), tx)))
			if result.status >= 400 {
				return errCommandRejected
			}
			return nil
		})
		if err != nil && !errors.Is(err, errCommandRejected) {
			fail(w, 500, "INTERNAL")
			return
		}
		for key, values := range result.header {
			w.Header()[key] = values
		}
		status := result.status
		if status == 0 {
			status = 204
		}
		w.WriteHeader(status)
		w.Write(result.body.Bytes())
	}
}
