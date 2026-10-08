package repository

import (
	"time"
	"errors"
	"context"
	"crypto/rand"
	"encoding/hex"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

var (
	ErrInvitationNotFound = errors.New("invitation link not found")
	ErrInvitationExpired  = errors.New("invitation link has expired")
	ErrInvitationInvalid  = errors.New("invitation link is no longer valid")
)

type InvitationRepository struct {
	db *gorm.DB
}

func NewInvitationRepository(db *gorm.DB) *InvitationRepository {
	return &InvitationRepository{db: db}
}

//  generates a secure random hex string
func GenerateToken() (string, error) {
	bytes := make([]byte, 16) // 32 char hex string
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return hex.EncodeToString(bytes), nil
}

func (r *InvitationRepository) Create(ctx context.Context, planID, createdBy uuid.UUID, ttl time.Duration, maxUses int) (*model.Invitation, error){
	token, err := GenerateToken()
	if err != nil {
		return nil, err
	}

	invitation := &model.Invitation{
		PlanID: planID,
		CreatedBy: createdBy,
		Token: token,
		Status: model.InvitationStatusPending,
		MaxUses: maxUses,
		ExpiresAt: time.Now().Add(ttl),
	}

	if err := r.db.WithContext(ctx).Create(invitation).Error; err != nil {
		return nil, err
	}
	return invitation, nil
}

// GetByToken fetches and validates an invitation token
func (r *InvitationRepository) GetByToken(ctx context.Context, token string) (*model.Invitation, error) {
	var invitation model.Invitation
	err := r.db.WithContext(ctx).
		Preload("Plan").
		First(&invitation, "token = ?", token).Error

	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrInvitationNotFound
		}
		return nil, err
	}

	// Validation checks
	if invitation.Status != model.InvitationStatusPending {
		return nil, ErrInvitationInvalid
	}
	if time.Now().After(invitation.ExpiresAt) {
		return nil, ErrInvitationExpired
	}
	if invitation.MaxUses > 0 && invitation.UseCount >= invitation.MaxUses {
		return nil, ErrInvitationInvalid
	}

	return &invitation, nil
}

// AcceptInvitation adds the user to plan_members and increments invitation usage in a transaction
func (r *InvitationRepository) AcceptInvitation(ctx context.Context, token string, userID uuid.UUID, displayName string) (*model.PlanMember, error) {
	var member model.PlanMember

	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var invitation model.Invitation
		if err := tx.Set("gorm:query_option", "FOR UPDATE").First(&invitation, "token = ?", token).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return ErrInvitationNotFound
			}
			return err
		}

		if invitation.Status != model.InvitationStatusPending || time.Now().After(invitation.ExpiresAt) {
			return ErrInvitationExpired
		}

		// 1. Check if user is already a member
		var existingCount int64
		tx.Model(&model.PlanMember{}).
			Where("plan_id = ? AND user_id = ?", invitation.PlanID, userID).
			Count(&existingCount)
		if existingCount > 0 {
			return errors.New("user is already a member of this plan")
		}

		// 2. Create the new PlanMember
		member = model.PlanMember{
			PlanID:      invitation.PlanID,
			UserID:      userID,
			DisplayName: displayName,
			Role:        model.MemberRoleMember,
		}
		if err := tx.Create(&member).Error; err != nil {
			return err
		}

		// 3. Increment invitation use count and update status if max uses reached
		invitation.UseCount++
		if invitation.MaxUses > 0 && invitation.UseCount >= invitation.MaxUses {
			invitation.Status = model.InvitationStatusAccepted
		}
		return tx.Save(&invitation).Error
	})

	if err != nil {
		return nil, err
	}

	return &member, nil
}