package repository

import (
	"context"
	"errors"
	"planning-service/app/internal/database"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

var (
	ErrPlanRoundNotFound = errors.New("plan round not found")
)

type PlanRoundRepository struct {
	db *gorm.DB
}

func NewPlanRoundRepository(db *gorm.DB) *PlanRoundRepository {
	return &PlanRoundRepository{db: db}
}

// Create creates a new round for a plan.
// Round number is automatically assigned based on the latest round.
func (r *PlanRoundRepository) Create(ctx context.Context, round *model.PlanRound) error {
	return database.ContextDB(ctx, r.db).Transaction(func(tx *gorm.DB) error {
		var plan model.Plan
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&plan, "id = ?", round.PlanID).Error; err != nil {
			return err
		}
		var active int64
		if err := tx.Table("integration_rounds").Where("plan_id = ? AND state IN ?", round.PlanID,
			[]string{"PUBLISHING", "COLLECTING", "LOCKING"}).Count(&active).Error; err != nil {
			return err
		}
		if active > 0 {
			return errors.New("close collection before creating another round")
		}
		var lastRound model.PlanRound
		err := tx.Where("plan_id = ?", round.PlanID).Order("round_number DESC").First(&lastRound).Error
		if errors.Is(err, gorm.ErrRecordNotFound) {
			round.RoundNumber = 1
		} else if err != nil {
			return err
		} else {
			round.RoundNumber = lastRound.RoundNumber + 1
		}
		return tx.Create(round).Error
	})
}

// GetByID fetches a single round by its primary key
func (r *PlanRoundRepository) GetByID(ctx context.Context, id uuid.UUID) (*model.PlanRound, error) {
	var round model.PlanRound

	err := database.ContextDB(ctx, r.db).
		First(&round, "id = ?", id).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrPlanRoundNotFound
		}

		return nil, err
	}

	return &round, nil
}

// ListByPlanID retrieves all rounds for a specific plan
func (r *PlanRoundRepository) ListByPlanID(ctx context.Context, planID uuid.UUID) ([]model.PlanRound, error) {
	var rounds []model.PlanRound

	err := database.ContextDB(ctx, r.db).
		Where("plan_id = ?", planID).
		Order("round_number ASC").
		Find(&rounds).Error

	return rounds, err
}

// Update updates a plan round
func (r *PlanRoundRepository) Update(ctx context.Context, id uuid.UUID, updates map[string]interface{}) (*model.PlanRound, error) {
	var round model.PlanRound

	if err := database.ContextDB(ctx, r.db).First(&round, "id = ?", id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrPlanRoundNotFound
		}

		return nil, err
	}

	if err := database.ContextDB(ctx, r.db).Model(&round).Updates(updates).Error; err != nil {
		return nil, err
	}

	return &round, nil
}

// Delete deletes a plan round
func (r *PlanRoundRepository) Delete(ctx context.Context, id uuid.UUID) error {
	result := database.ContextDB(ctx, r.db).Delete(&model.PlanRound{}, "id = ?", id)

	if result.Error != nil {
		return result.Error
	}

	if result.RowsAffected == 0 {
		return ErrPlanRoundNotFound
	}

	return nil
}
