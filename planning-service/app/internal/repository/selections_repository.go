package repository

import (
	"context"
	"errors"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

var (
	ErrConfirmedSelectionNotFound = errors.New("confirmed selection not found")
	ErrConfirmedSelectionExists   = errors.New("confirmed selection already exists for this plan")
)

type ConfirmedSelectionRepository struct {
	db *gorm.DB
}

func NewConfirmedSelectionRepository(db *gorm.DB) *ConfirmedSelectionRepository {
	return &ConfirmedSelectionRepository{db: db}
}

// Create creates a confirmed selection for a plan
func (r *ConfirmedSelectionRepository) Create(ctx context.Context, selection *model.ConfirmedSelection) error {
	var count int64

	err := r.db.WithContext(ctx).
		Model(&model.ConfirmedSelection{}).
		Where("plan_id = ?", selection.PlanID).
		Count(&count).Error

	if err != nil {
		return err
	}

	if count > 0 {
		return ErrConfirmedSelectionExists
	}

	return r.db.WithContext(ctx).Create(selection).Error
}

// GetByID fetches a confirmed selection by its ID
func (r *ConfirmedSelectionRepository) GetByID(ctx context.Context, id uuid.UUID) (*model.ConfirmedSelection, error) {
	var selection model.ConfirmedSelection

	err := r.db.WithContext(ctx).
		Preload("SelectedActivity").
		First(&selection, "id = ?", id).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrConfirmedSelectionNotFound
		}

		return nil, err
	}

	return &selection, nil
}

// GetByPlanID fetches the confirmed selection for a plan
func (r *ConfirmedSelectionRepository) GetByPlanID(ctx context.Context, planID uuid.UUID) (*model.ConfirmedSelection, error) {
	var selection model.ConfirmedSelection

	err := r.db.WithContext(ctx).
		Preload("SelectedActivity").
		First(&selection, "plan_id = ?", planID).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrConfirmedSelectionNotFound
		}

		return nil, err
	}

	return &selection, nil
}