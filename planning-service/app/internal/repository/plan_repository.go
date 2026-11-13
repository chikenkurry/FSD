package repository

import (
	"context"
	"errors"
	"planning-service/app/internal/database"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

var ErrPlanNotFound = errors.New("plan not found")

type PlanRepository struct {
	db *gorm.DB
}

func NewPlanRepository(db *gorm.DB) *PlanRepository {
	return &PlanRepository{db: db}
}

// inserts a new plan row
func (r *PlanRepository) CreatePlan(ctx context.Context, plan *model.Plan, organiserName string) error {
	return database.ContextDB(ctx, r.db).Transaction(func(tx *gorm.DB) error {
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

// GetPlanById finds a plan by primary key
func (r *PlanRepository) GetPlanById(ctx context.Context, id uuid.UUID) (*model.Plan, error) {
	var plan model.Plan
	err := database.ContextDB(ctx, r.db).First(&plan, "id = ?", id).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrPlanNotFound
		}
		return nil, err
	}
	return &plan, nil
}

// GetByIDWithDetails preloads all related rounds, members, activities, and selections
func (r *PlanRepository) GetByIDWithDetails(ctx context.Context, id uuid.UUID) (*model.Plan, error) {
	var plan model.Plan
	err := database.ContextDB(ctx, r.db).
		Preload("Rounds").
		Preload("Members").
		Preload("ProposedActivities").
		Preload("Questions").
		First(&plan, "id = ?", id).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrPlanNotFound
		}
		return nil, err
	}
	var selected model.RoundSelection
	if err := database.ContextDB(ctx, r.db).Where("plan_id = ?", id).Order("version DESC").First(&selected).Error; err == nil {
		plan.ConfirmedSelection = &selected
	} else if !errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, err
	}
	return &plan, nil
}

// ListByOrganiser queries plans for a specific user
func (r *PlanRepository) ListByOrganiser(ctx context.Context, organiserID uuid.UUID, limit, offset int) ([]model.Plan, error) {
	var plans []model.Plan
	err := database.ContextDB(ctx, r.db).
		Where("created_by_user_id = ?", organiserID).
		Order("created_at DESC").
		Limit(limit).
		Offset(offset).
		Preload("CreatedBy").
		Preload("Members", func(db *gorm.DB) *gorm.DB { return db.Select("id", "plan_id") }).
		Find(&plans).Error

	return plans, err
}

// ListByMember queries plans the user belongs to
func (r *PlanRepository) ListByMember(ctx context.Context, memberID uuid.UUID, limit, offset int) ([]model.Plan, error) {
	var plans []model.Plan
	err := database.ContextDB(ctx, r.db).Where("id IN (SELECT plan_id FROM plan_members WHERE user_id = ?)", memberID).
		Order("created_at DESC").Limit(limit).Offset(offset).Preload("CreatedBy").
		Preload("Members", func(db *gorm.DB) *gorm.DB { return db.Select("id", "plan_id") }).Find(&plans).Error
	return plans, err
}

// update updates non-empty fields of a plan
func (r *PlanRepository) Update(ctx context.Context, id uuid.UUID, updates map[string]interface{}) (*model.Plan, error) {
	var plan model.Plan

	// Ensure plan exists
	if err := database.ContextDB(ctx, r.db).First(&plan, "id = ?", id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrPlanNotFound
		}
		return nil, err
	}

	// Apply updates
	if err := database.ContextDB(ctx, r.db).Model(&plan).Updates(updates).Error; err != nil {
		return nil, err
	}

	return &plan, nil
}

// Delete removes a plan (cascades via database foreign key definitions)
func (r *PlanRepository) Delete(ctx context.Context, id uuid.UUID) error {
	result := database.ContextDB(ctx, r.db).Delete(&model.Plan{}, "id = ?", id)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return ErrPlanNotFound
	}
	return nil
}
