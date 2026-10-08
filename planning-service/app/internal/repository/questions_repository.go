package repository

import (
	"context"
	"errors"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

var ErrQuestionNotFound = errors.New("question not found")

type QuestionRepository struct {
	db *gorm.DB
}

func NewQuestionRepository(db *gorm.DB) *QuestionRepository {
	return &QuestionRepository{db: db}
}

// insert a single question 
func (r *QuestionRepository) Create(ctx context.Context, q *model.Question) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		// If sort_order was not provided (or is set to 0)
		if q.SortOrder == 0 {
			var maxSortOrder *int
			
			// COALESCE returns 0 if MAX() returns NULL (when no questions exist yet)
			err := tx.Model(&model.Question{}).
				Where("plan_id = ?", q.PlanID).
				Select("COALESCE(MAX(sort_order), 0)").
				Scan(&maxSortOrder).Error

			if err != nil {
				return err
			}

			q.SortOrder = *maxSortOrder + 1
		}

		return tx.Create(q).Error
	})
}

// CreateBatch seeds a list of questions (e.g. default form template) for a plan
func (r *QuestionRepository) CreateBatch(ctx context.Context, questions []model.Question) error {
	return r.db.WithContext(ctx).Create(&questions).Error
}

// ListByPlanID returns all questions for a given plan ordered by form position
func (r *QuestionRepository) ListByPlanID(ctx context.Context, planID uuid.UUID) ([]model.Question, error) {
	var questions []model.Question
	err := r.db.WithContext(ctx).
		Where("plan_id = ?", planID).
		Order("sort_order ASC").
		Find(&questions).Error
	return questions, err
}

// Update modifies question title, requirement status, options, or sort order
func (r *QuestionRepository) Update(ctx context.Context, id uuid.UUID, updates map[string]interface{}) (*model.Question, error) {
	var q model.Question
	if err := r.db.WithContext(ctx).First(&q, "id = ?", id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrQuestionNotFound
		}
		return nil, err
	}

	if err := r.db.WithContext(ctx).Model(&q).Updates(updates).Error; err != nil {
		return nil, err
	}
	return &q, nil
}

// Delete removes a question by ID
func (r *QuestionRepository) Delete(ctx context.Context, id uuid.UUID) error {
	res := r.db.WithContext(ctx).Delete(&model.Question{}, "id = ?", id)
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return ErrQuestionNotFound
	}
	return nil
}