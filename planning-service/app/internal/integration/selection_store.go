package integration

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/datatypes"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

func (s *roundStore) findSelection(ctx context.Context, id uuid.UUID) (Selection, error) {
	var selection Selection
	err := s.db.WithContext(ctx).First(&selection, "round_id = ?", id).Error
	return selection, err
}

func (s *roundStore) confirm(ctx context.Context, round Round, request confirmationRequest, user uuid.UUID, details datatypes.JSON) (Selection, error) {
	id := round.ID
	selection := Selection{RoundID: id, PlanID: round.PlanID, Version: round.OptionRevision, OptionSnapshotID: round.OptionSnapshotID, ResponseSnapshotID: round.ResponseSnapshotID, Details: details, OperationID: request.OperationID, RunID: request.RunID, CandidateID: request.CandidateID, ConfirmedBy: user, ConfirmedAt: time.Now().UTC().Truncate(time.Microsecond)}
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var current Round
		if err := lockPublishedRound(tx, id, &current); err != nil {
			return err
		}
		var plan model.Plan
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&plan, "id = ?", current.PlanID).Error; err != nil {
			return err
		}
		if current.State == roundConfirmed {
			if err := tx.First(&selection, "round_id = ?", id).Error; err != nil {
				return err
			}
			if !selectionMatches(selection, request) {
				return fmt.Errorf("operation conflict")
			}
			return nil
		}
		latest, err := latestPlanRound(tx, current.PlanID)
		if err != nil {
			return err
		}
		if latest.ID != id {
			return fmt.Errorf("newer round exists")
		}
		if current.State != roundReview || current.LastRunID != request.RunID || current.ResponseSnapshotID != round.ResponseSnapshotID {
			return fmt.Errorf("stale result")
		}
		if err := tx.Create(&selection).Error; err != nil {
			return err
		}
		if err := tx.Model(&current).Update("state", roundConfirmed).Error; err != nil {
			return err
		}
		return tx.Model(&model.Plan{}).Where("id = ?", current.PlanID).Update("state", model.PlanStateConfirmed).Error
	})
	return selection, err
}

func (s *roundStore) reopen(ctx context.Context, id uuid.UUID, operationID uuid.UUID) (model.PlanRound, error) {
	var created model.PlanRound
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var source Round
		if err := lockPublishedRound(tx, id, &source); err != nil {
			return err
		}
		if source.State != roundReview && source.State != roundConfirmed {
			return fmt.Errorf("close collection before reopening")
		}
		var plan model.Plan
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&plan, "id = ?", source.PlanID).Error; err != nil {
			return err
		}
		var operation ReopenOperation
		if tx.First(&operation, "operation_id = ?", operationID).Error == nil {
			if operation.SourceRoundID != id {
				return fmt.Errorf("operation conflict")
			}
			return tx.First(&created, "id = ?", operation.NewRoundID).Error
		}
		latest, err := latestPlanRound(tx, source.PlanID)
		if err != nil {
			return err
		}
		if latest.ID != id {
			return fmt.Errorf("a newer round already exists")
		}
		created = model.PlanRound{ID: uuid.New(), PlanID: source.PlanID, RoundNumber: latest.RoundNumber + 1, IsActive: false,
			CreatorState: latest.CreatorState, SourceRoundID: &source.ID}
		if err := tx.Create(&created).Error; err != nil {
			return err
		}
		if err := tx.Create(&ReopenOperation{OperationID: operationID, SourceRoundID: id, NewRoundID: created.ID}).Error; err != nil {
			return err
		}
		return tx.Model(&plan).Update("state", model.PlanStateDraft).Error
	})
	return created, err
}

func selectionMatches(s Selection, request confirmationRequest) bool {
	var details struct {
		EventDate string `json:"event_date"`
		EventTime string `json:"event_time"`
	}
	_ = json.Unmarshal(s.Details, &details)
	return s.OperationID == request.OperationID && s.RunID == request.RunID && s.CandidateID == request.CandidateID &&
		details.EventDate == request.EventDate && details.EventTime == request.EventTime
}
