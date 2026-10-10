package repository

import (
	"context"
	"errors"

	"planning-service/app/internal/model"
	
	"github.com/google/uuid"
	"gorm.io/gorm"
)

var ErrPlanNotFound = errors.New("plan not found")

type PlanRepository struct {
	db *gorm.DB
}

func NewPlanRepository(db *gorm.DB) *PlanRepository{
	return &PlanRepository{db: db}
}

// inserts a new plan row
func (r *PlanRepository) CreatePlan(ctx context.Context, plan *model.Plan, organiserName string) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(plan).Error; err != nil {
			return err
		}

		member := model.PlanMember{
			PlanID:      plan.ID,
			UserID:      plan.CreatedByUserID,
			DisplayName: organiserName,
			Role:        model.MemberRoleOrganiser,
		}

		if err := tx.Create(&member).Error; err != nil {
			return err
		}

		return nil
	})
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

// GetByIDWithDetails preloads all related rounds, members, activities, and selections
func (r *PlanRepository) GetByIDWithDetails(ctx context.Context, id uuid.UUID) (*model.Plan, error) {
	var plan model.Plan
	err := r.db.WithContext(ctx).
		Preload("Rounds").
		Preload("Members").
		Preload("ProposedActivities").
		Preload("Questions").
		Preload("ConfirmedSelection").
		First(&plan, "id = ?", id).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrPlanNotFound
		}
		return nil, err
	}
	return &plan, nil
}

// ListByOrganiser queries plans for a specific user
func (r *PlanRepository) ListByOrganiser(ctx context.Context, organiserID string, limit, offset int) ([]model.Plan, error) {
	var plans []model.Plan
	err := r.db.WithContext(ctx).
		Where("created_by_user_id = ?", organiserID).
		Order("created_at DESC").
		Limit(limit).
		Offset(offset).
		Find(&plans).Error

	return plans, err
}


// update updates non-empty fields of a plan
func (r *PlanRepository) Update(ctx context.Context, id uuid.UUID, updates map[string]interface{}) (*model.Plan, error) {
	var plan model.Plan
	
	// Ensure plan exists
	if err := r.db.WithContext(ctx).First(&plan, "id = ?", id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrPlanNotFound
		}
		return nil, err
	}

	// Apply updates
	if err := r.db.WithContext(ctx).Model(&plan).Updates(updates).Error; err != nil {
		return nil, err
	}

	return &plan, nil
}

// Delete removes a plan (cascades via database foreign key definitions)
func (r *PlanRepository) Delete(ctx context.Context, id uuid.UUID) error {
	result := r.db.WithContext(ctx).Delete(&model.Plan{}, "id = ?", id)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return ErrPlanNotFound
	}
	return nil
}
