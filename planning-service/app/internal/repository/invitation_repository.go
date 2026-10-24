package repository

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"planning-service/app/internal/database"
	"time"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

var (
	ErrJoiningClosed      = errors.New("joining is closed for this round")
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

// generates a secure random hex string
func GenerateToken() (string, error) {
	bytes := make([]byte, 16) // 32 char hex string
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return hex.EncodeToString(bytes), nil
}

func (r *InvitationRepository) Create(ctx context.Context, planID, createdBy uuid.UUID, ttl time.Duration, maxUses int) (*model.Invitation, error) {
	token, err := GenerateToken()
	if err != nil {
		return nil, err
	}

	invitation := &model.Invitation{
		PlanID:    planID,
		CreatedBy: createdBy,
		Token:     token,
		Status:    model.InvitationStatusPending,
		MaxUses:   maxUses,
		ExpiresAt: time.Now().Add(ttl),
	}

	if err := database.ContextDB(ctx, r.db).Create(invitation).Error; err != nil {
		return nil, err
	}
	return invitation, nil
}

// GetByToken fetches and validates an invitation token
func (r *InvitationRepository) GetByToken(ctx context.Context, token string) (*model.Invitation, error) {
	var invitation model.Invitation
	err := database.ContextDB(ctx, r.db).
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

	err := database.ContextDB(ctx, r.db).Transaction(func(tx *gorm.DB) error {
		var invitation model.Invitation
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&invitation, "token = ?", token).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return ErrInvitationNotFound
			}
			return err
		}

		if invitation.Status != model.InvitationStatusPending || time.Now().After(invitation.ExpiresAt) {
			return ErrInvitationExpired
		}
		if invitation.MaxUses > 0 && invitation.UseCount >= invitation.MaxUses {
			return ErrInvitationInvalid
		}
		var plan model.Plan
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&plan, "id = ?", invitation.PlanID).Error; err != nil {
			return err
		}
		var latest model.PlanRound
		if err := tx.Where("plan_id = ?", plan.ID).Order("round_number DESC").First(&latest).Error; err == nil {
			var published model.PublishedRound
			if err := tx.First(&published, "id = ?", latest.ID).Error; err == nil &&
				(published.State != "COLLECTING" || published.RosterPolicy != "close") {
				return ErrJoiningClosed
			} else if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
				return err
			}
		}
		var count int64
		if err := tx.Model(&model.PlanMember{}).Where("plan_id = ?", plan.ID).Count(&count).Error; err != nil {
			return err
		}
		if count >= 30 {
			return errors.New("plan roster is full")
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
