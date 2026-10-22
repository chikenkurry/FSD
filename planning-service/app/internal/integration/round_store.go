package integration

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"sort"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

// Transactions serialize round transitions; upstream calls remain outside locks.
type roundStore struct{ db *gorm.DB }

// All lifecycle commands acquire plan before published-round, matching definition
// edits and invitation admission. Consistent order prevents confirm/reopen deadlocks.
func lockPublishedRound(tx *gorm.DB, id uuid.UUID, target *Round) error {
	if err := tx.First(target, "id = ?", id).Error; err != nil {
		return err
	}
	var plan model.Plan
	if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&plan, "id = ?", target.PlanID).Error; err != nil {
		return err
	}
	return tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(target, "id = ?", id).Error
}

func (s *roundStore) find(ctx context.Context, id uuid.UUID) (Round, error) {
	var round Round
	err := s.db.WithContext(ctx).First(&round, "id = ?", id).Error
	return round, err
}

func (s *roundStore) abandonPublication(ctx context.Context, id uuid.UUID) {
	s.db.WithContext(ctx).Delete(&Round{}, "id = ? AND state = ?", id, roundPublishing)
}

func (s *roundStore) preparePublication(ctx context.Context, id uuid.UUID, settings Settings) (Round, error) {
	var round Round
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var source model.PlanRound
		if err := tx.First(&source, "id = ?", id).Error; err != nil {
			return err
		}
		var gate model.Plan
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&gate, "id = ?", source.PlanID).Error; err != nil {
			return err
		}
		existing := tx.First(&round, "id = ?", id).Error
		if existing == nil {
			if !sameJSON(round.Settings, encoded(settings)) {
				return fmt.Errorf("publish settings changed; create a new round")
			}
			if round.State != roundPublishing && round.State != roundCollecting {
				return fmt.Errorf("round already closed")
			}
			return nil
		}
		if !errors.Is(existing, gorm.ErrRecordNotFound) {
			return existing
		}
		var plan model.Plan
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Preload("Members").Preload("Questions").Preload("ProposedActivities").First(&plan, "id = ?", source.PlanID).Error; err != nil {
			return err
		}
		latest, err := latestPlanRound(tx, plan.ID)
		if err != nil {
			return err
		}
		if latest.ID != id {
			return fmt.Errorf("a newer draft round exists")
		}
		var active int64
		if err := tx.Model(&Round{}).Where("plan_id = ? AND state IN ?", plan.ID, []string{roundPublishing, roundCollecting, roundLocking}).Count(&active).Error; err != nil {
			return err
		}
		if active > 0 {
			return fmt.Errorf("another round is collecting")
		}
		snapshotID := uuid.New()
		snapshot, err := BuildSnapshot(plan, source, snapshotID, settings)
		if err != nil {
			return err
		}
		round = Round{ID: id, PlanID: plan.ID, State: roundPublishing, RosterPolicy: "close", OptionRevision: source.RoundNumber, OptionSnapshotID: snapshotID,
			Definition: encoded(snapshot), Settings: encoded(settings), PublishOperationID: uuid.New(), FreezeOperationID: uuid.New()}
		return tx.Create(&round).Error
	}, &sql.TxOptions{Isolation: sql.LevelSerializable})
	return round, err
}

func (s *roundStore) finalizePublication(ctx context.Context, id uuid.UUID) (Round, error) {
	var round Round
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := lockPublishedRound(tx, id, &round); err != nil {
			return err
		}
		if round.State != roundPublishing {
			return nil
		}
		if err := tx.Model(&round).Update("state", roundCollecting).Error; err != nil {
			return err
		}
		if err := tx.Model(&model.PlanRound{}).Where("id = ?", id).Update("is_active", true).Error; err != nil {
			return err
		}
		return tx.Model(&model.Plan{}).Where("id = ?", round.PlanID).Update("state", model.PlanStateCollecting).Error
	})
	return round, err
}

func (s *roundStore) beginFreeze(ctx context.Context, id uuid.UUID) (Round, error) {
	var round Round
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := lockPublishedRound(tx, id, &round); err != nil {
			return err
		}
		if round.State == roundReview || round.State == roundConfirmed {
			return nil
		}
		if round.State != roundCollecting && round.State != roundLocking {
			return fmt.Errorf("round not collecting")
		}
		if round.State == roundLocking {
			return nil
		}
		// The plan row also serializes invitation admission. A join committed first is included.
		var plan model.Plan
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Preload("Members").First(&plan, "id = ?", round.PlanID).Error; err != nil {
			return err
		}
		if round.RosterPolicy == "close" {
			roster := make([]string, 0, len(plan.Members))
			for _, member := range plan.Members {
				roster = append(roster, member.UserID.String())
			}
			sort.Strings(roster)
			if len(roster) == 0 || len(roster) > 30 {
				return fmt.Errorf("invalid final roster")
			}
			var evaluation map[string]any
			if err := json.Unmarshal(round.Definition, &evaluation); err != nil {
				return err
			}
			round.OptionSnapshotID = uuid.New()
			evaluation["roster"], evaluation["option_snapshot_id"] = roster, round.OptionSnapshotID.String()
			evaluation["roster_is_final"] = true
			round.EvaluationDefinition = encoded(evaluation)
			if err := tx.Model(&round).Updates(map[string]any{"option_snapshot_id": round.OptionSnapshotID, "evaluation_definition": round.EvaluationDefinition}).Error; err != nil {
				return err
			}
		}
		return tx.Model(&round).Update("state", roundLocking).Error
	})
	return round, err
}

func (s *roundStore) finalizeFreeze(ctx context.Context, id uuid.UUID, snapshotID string) (Round, error) {
	var round Round
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := lockPublishedRound(tx, id, &round); err != nil {
			return err
		}
		if round.State != roundLocking {
			if round.ResponseSnapshotID != snapshotID {
				return fmt.Errorf("freeze reference changed")
			}
			return nil
		}
		if err := tx.Model(&round).Updates(map[string]any{"state": roundReview, "response_snapshot_id": snapshotID}).Error; err != nil {
			return err
		}
		if err := tx.Model(&model.PlanRound{}).Where("id = ?", id).Update("is_active", false).Error; err != nil {
			return err
		}
		return tx.Model(&model.Plan{}).Where("id = ?", round.PlanID).Update("state", model.PlanStateReviewing).Error
	})
	return round, err
}

func (s *roundStore) cancelFreeze(ctx context.Context, attempted Round) error {
	return s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var current Round
		if err := lockPublishedRound(tx, attempted.ID, &current); err != nil {
			return err
		}
		if current.State != roundLocking || current.FreezeOperationID != attempted.FreezeOperationID {
			return nil
		}
		var form struct {
			OptionSnapshotID uuid.UUID `json:"option_snapshot_id"`
		}
		if err := json.Unmarshal(current.Definition, &form); err != nil {
			return err
		}
		return tx.Model(&current).Updates(map[string]any{"state": roundCollecting, "evaluation_definition": nil,
			"option_snapshot_id": form.OptionSnapshotID, "freeze_operation_id": uuid.New()}).Error
	})
}

func (s *roundStore) saveRecommendation(ctx context.Context, round Round, runID string) error {
	id := round.ID
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var current Round
		if err := lockPublishedRound(tx, id, &current); err != nil {
			return err
		}
		var plan model.Plan
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&plan, "id = ?", current.PlanID).Error; err != nil {
			return err
		}
		latest, err := latestPlanRound(tx, current.PlanID)
		if err != nil {
			return err
		}
		if current.State != roundReview || latest.ID != id || current.ResponseSnapshotID != round.ResponseSnapshotID {
			return fmt.Errorf("round changed during recommendation")
		}
		return tx.Model(&current).Update("last_run_id", runID).Error
	})
	return err
}

func (s *roundStore) latestRound(ctx context.Context, round Round) bool {
	latest, err := latestPlanRound(s.db.WithContext(ctx), round.PlanID)
	return err == nil && latest.ID == round.ID
}

func latestPlanRound(db *gorm.DB, planID uuid.UUID) (model.PlanRound, error) {
	var latest model.PlanRound
	err := db.Where("plan_id = ?", planID).Order("round_number DESC").First(&latest).Error
	return latest, err
}
