package repository

import (
	"context"
	"errors"
	"planning-service/app/internal/database"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

var ErrProposedActivityNotFound = errors.New("proposed activity not found")

type ProposedActivityRepository struct {
	db *gorm.DB
}

func NewProposedActivityRepository(db *gorm.DB) *ProposedActivityRepository {
	return &ProposedActivityRepository{db: db}
}

func (r *ProposedActivityRepository) Create(ctx context.Context, activity *model.ProposedActivity) error {
	return database.ContextDB(ctx, r.db).Create(activity).Error
}

func (r *ProposedActivityRepository) GetByID(ctx context.Context, id uuid.UUID) (*model.ProposedActivity, error) {
	var activity model.ProposedActivity

	err := database.ContextDB(ctx, r.db).First(&activity, "id = ?", id).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrProposedActivityNotFound
		}
		return nil, err
	}

	return &activity, nil
}

// retrieves all activities for a specific plan
func (r *ProposedActivityRepository) ListByPlanID(ctx context.Context, planID uuid.UUID) ([]model.ProposedActivity, error) {
	var activities []model.ProposedActivity

	err := database.ContextDB(ctx, r.db).
		Where("plan_id = ?", planID).
		Order("created_at ASC").
		Find(&activities).Error

	return activities, err
}

func (r *ProposedActivityRepository) Update(ctx context.Context, id uuid.UUID, updates map[string]interface{}) (*model.ProposedActivity, error) {
	var activity model.ProposedActivity

	if err := database.ContextDB(ctx, r.db).First(&activity, "id = ?", id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrProposedActivityNotFound
		}
		return nil, err
	}

	if err := database.ContextDB(ctx, r.db).Model(&activity).Updates(updates).Error; err != nil {
		return nil, err
	}

	return &activity, nil
}

func (r *ProposedActivityRepository) Delete(ctx context.Context, id uuid.UUID) error {
	result := database.ContextDB(ctx, r.db).Delete(&model.ProposedActivity{}, "id = ?", id)

	if result.Error != nil {
		return result.Error
	}

	if result.RowsAffected == 0 {
		return ErrProposedActivityNotFound
	}

	return nil
}
