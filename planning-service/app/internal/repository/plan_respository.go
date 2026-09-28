package repository

import (
	"context"
	"errors"

	"planning-service/app/internal/model"
	
	"gorm.io/gorm"
)

type PlanRepository struct {
	db *gorm.DB
}

func NewPlanRepository(db *gorm.DB) *PlanRepository{
	return &PlanRepository{db: db}
}

// inserts a new plan row
func (r *PlanRepository) CreatePlan(ctx context.Context, plan *model.Plan) error {
	return r.db.WithContext(ctx).Create(plan).Error
}

// GetByID finds a plan by primary key
func (r *PlanRepository) GetPlanById(ctx context.Context, id string) (*model.Plan, error) {
	var plan model.Plan
	err := r.db.WithContext(ctx).First(&plan, "id = ?", id).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, errors.New("plan not found")
		}
		return nil, err
	}
	return &plan, nil
}

// ListByOrganiser queries plans for a specific user
func (r *PlanRepository) ListByOrganiser(ctx context.Context, organiserID string, limit, offset int) ([]model.Plan, error) {
	var plans []model.Plan
	err := r.db.WithContext(ctx).
		Where("organiser_id = ?", organiserID).
		Order("created_at DESC").
		Limit(limit).
		Offset(offset).
		Find(&plans).Error

	return plans, err
}


// update updates non-empty fields of a plan
func (r *PlanRepository) UpdatePlan(ctx context.Context, plan *model.Plan) error {
	result := r.db.WithContext(ctx).Model(plan).Updates(plan)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return errors.New("plan not found to update")
	}
	return nil
}