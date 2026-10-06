package model

import (
	"time"

	"github.com/google/uuid"
)

type InvitationStatus string

const (
	InvitationStatusPending  InvitationStatus = "PENDING"
	InvitationStatusAccepted InvitationStatus = "ACCEPTED"
	InvitationStatusRevoked  InvitationStatus = "REVOKED"
	InvitationStatusExpired  InvitationStatus = "EXPIRED"
)

type Invitation struct {
	ID        uuid.UUID        `gorm:"type:uuid;default:gen_random_uuid();primaryKey" json:"id"`
	PlanID    uuid.UUID        `gorm:"type:uuid;not null;index:idx_invitations_plan_status,priority:1" json:"plan_id"`
	TokenHash string           `gorm:"type:varchar(64);not null;uniqueIndex" json:"token_hash"`
	Email     *string          `gorm:"type:varchar(255)" json:"email,omitempty"`
	Status    InvitationStatus `gorm:"type:varchar(50);default:'PENDING';not null;index:idx_invitations_plan_status,priority:2" json:"status"`
	ExpiresAt time.Time        `gorm:"type:timestamptz;not null" json:"expires_at"`
	CreatedAt time.Time        `gorm:"type:timestamptz;not null;default:CURRENT_TIMESTAMP" json:"created_at"`
}

func (Invitation) TableName() string {
	return "invitations"
}