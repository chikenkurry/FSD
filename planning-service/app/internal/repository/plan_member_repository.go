package repository

import (
	"context"
	"errors"

	"planning-service/app/internal/model"

	"gorm.io/gorm"
	"github.com/google/uuid"
)

var (
	ErrMemberNotFound  = errors.New("plan member not found")
	ErrMemberExists    = errors.New("user is already a member of this plan")
)

type PlanMemberRepository struct {
	db *gorm.DB
}

func NewPlanMemberRepository(db *gorm.DB) *PlanMemberRepository{
	return &PlanMemberRepository{db: db}
}

// AddMember adds a user to a plan
func (r *PlanMemberRepository) AddMember(ctx context.Context, member *model.PlanMember) error {
	// check if user is already a member of this plan
	var count int64
	err := r.db.WithContext(ctx).
			Model(&model.PlanMember{}).
			Where("plan_id = ? AND user_id = ?", member.PlanID, member.UserID).
			Count(&count).Error
	
	if err != nil {
		return err
	}
	if count > 0 {
		return ErrMemberExists
	}

	return r.db.WithContext(ctx).Create(member).Error
}

// GetMemberByID fetches a single plan member record by its primary key
func (r *PlanMemberRepository) GetMemberByID(ctx context.Context, id uuid.UUID) (*model.PlanMember, error) {
	var member model.PlanMember
	err := r.db.WithContext(ctx).
		Preload("User").
		First(&member, "id = ?", id).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrMemberNotFound
		}
		return nil, err
	}
	return &member, nil
}

// ListByPlanID retrieves all members for a specific plan
func (r *PlanMemberRepository) ListByPlanID(ctx context.Context, planID uuid.UUID) ([]model.PlanMember, error) {
	var members []model.PlanMember
	err := r.db.WithContext(ctx).
		Preload("User").
		Where("plan_id = ?", planID).
		Order("joined_at ASC").
		Find(&members).Error

	return members, err
}

// UpdateMember updates display name and/or role of a plan member
func (r *PlanMemberRepository) UpdateMember(ctx context.Context, id uuid.UUID, updates map[string]interface{}) (*model.PlanMember, error) {
	var member model.PlanMember
	
	if err := r.db.WithContext(ctx).First(&member, "id = ?", id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrMemberNotFound
		}
		return nil, err
	}

	if err := r.db.WithContext(ctx).Model(&member).Updates(updates).Error; err != nil {
		return nil, err
	}

	return &member, nil
}

// RemoveMember removes a member from a plan by primary key
func (r *PlanMemberRepository) RemoveMember(ctx context.Context, id uuid.UUID) error {
	result := r.db.WithContext(ctx).Delete(&model.PlanMember{}, "id = ?", id)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return ErrMemberNotFound
	}
	return nil
}

// RemoveMemberByPlanAndUser removes a member using plan_id and user_id
func (r *PlanMemberRepository) RemoveMemberByPlanAndUser(ctx context.Context, planID, userID uuid.UUID) error {
	result := r.db.WithContext(ctx).
		Where("plan_id = ? AND user_id = ?", planID, userID).
		Delete(&model.PlanMember{})

	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return ErrMemberNotFound
	}
	return nil
}