package model

import (
	"time"

	"github.com/google/uuid"
)

type InvitationStatus string

const (
	InvitationStatusPending InvitationStatus = "PENDING"
	InvitationStatusAccepted InvitationStatus = "ACCEPTED"
	InvitationStatusRevoked  InvitationStatus = "REVOKED"
	InvitationStatusExpired  InvitationStatus = "EXPIRED"
)

type Invitation struct {
	ID        uuid.UUID        `gorm:"type:uuid;primaryKey;default:gen_random_uuid()" json:"id"`
	PlanID    uuid.UUID        `gorm:"type:uuid;not null;index" json:"plan_id"`
	CreatedBy uuid.UUID        `gorm:"type:uuid;not null" json:"created_by"`
	Token     string           `gorm:"type:varchar(64);uniqueIndex;not null" json:"token"`
	Status    InvitationStatus `gorm:"type:varchar(20);default:'PENDING';not null" json:"status"`
	ExpiresAt time.Time        `gorm:"not null" json:"expires_at"`
	CreatedAt time.Time        `gorm:"autoCreateTime" json:"created_at"`

	// Optional limits
	MaxUses  int `gorm:"default:0" json:"max_uses"`  // 0 = unlimited
	UseCount int `gorm:"default:0" json:"use_count"`

	// Relations
	Plan *Plan `gorm:"foreignKey:PlanID;references:ID;constraint:OnDelete:CASCADE" json:"-"`
}