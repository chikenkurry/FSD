package repository

import (
	"context"
	"errors"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
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
	var lastRound model.PlanRound

	err := r.db.WithContext(ctx).
		Where("plan_id = ?", round.PlanID).
		Order("round_number DESC").
		First(&lastRound).Error

	if errors.Is(err, gorm.ErrRecordNotFound) {
		round.RoundNumber = 1
	} else if err != nil {
		return err
	} else {
		round.RoundNumber = lastRound.RoundNumber + 1
	}

	return r.db.WithContext(ctx).Create(round).Error
}

// GetByID fetches a single round by its primary key
func (r *PlanRoundRepository) GetByID(ctx context.Context, id uuid.UUID) (*model.PlanRound, error) {
	var round model.PlanRound

	err := r.db.WithContext(ctx).
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

	err := r.db.WithContext(ctx).
		Where("plan_id = ?", planID).
		Order("round_number ASC").
		Find(&rounds).Error

	return rounds, err
}

// Update updates a plan round
func (r *PlanRoundRepository) Update(ctx context.Context, id uuid.UUID, updates map[string]interface{}) (*model.PlanRound, error) {
	var round model.PlanRound

	if err := r.db.WithContext(ctx).First(&round, "id = ?", id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrPlanRoundNotFound
		}

		return nil, err
	}

	if err := r.db.WithContext(ctx).Model(&round).Updates(updates).Error; err != nil {
		return nil, err
	}

	return &round, nil
}

// Delete deletes a plan round
func (r *PlanRoundRepository) Delete(ctx context.Context, id uuid.UUID) error {
	result := r.db.WithContext(ctx).Delete(&model.PlanRound{}, "id = ?", id)

	if result.Error != nil {
		return result.Error
	}

	if result.RowsAffected == 0 {
		return ErrPlanRoundNotFound
	}

	return nil
}