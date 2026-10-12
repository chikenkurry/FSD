package integration

import (
	"time"

	"github.com/google/uuid"
	"gorm.io/datatypes"
)

const (
	roundPublishing = "PUBLISHING"
	roundCollecting = "COLLECTING"
	roundLocking    = "LOCKING"
	roundReview     = "REVIEW"
	roundConfirmed  = "CONFIRMED"
)

type Session struct {
	TokenHash string    `gorm:"primaryKey" json:"-"`
	UserID    uuid.UUID `gorm:"type:uuid;not null;index" json:"-"`
	ExpiresAt time.Time `gorm:"not null" json:"-"`
}

type Round struct {
	ID                 uuid.UUID      `gorm:"type:uuid;primaryKey" json:"round_id"`
	PlanID             uuid.UUID      `gorm:"type:uuid;not null;index" json:"plan_id"`
	State              string         `gorm:"not null" json:"state"`
	OptionRevision     int            `gorm:"not null" json:"option_revision"`
	OptionSnapshotID   uuid.UUID      `gorm:"type:uuid;not null" json:"option_snapshot_id"`
	Definition         datatypes.JSON `gorm:"type:jsonb;not null" json:"-"`
	Settings           datatypes.JSON `gorm:"type:jsonb;not null" json:"-"`
	PublishOperationID uuid.UUID      `gorm:"type:uuid;not null" json:"-"`
	FreezeOperationID  uuid.UUID      `gorm:"type:uuid;not null" json:"-"`
	ResponseSnapshotID string         `json:"response_snapshot_id,omitempty"`
	LastRunID          string         `json:"recommendation_run_id,omitempty"`
}

func (Round) TableName() string { return "integration_rounds" }

type Selection struct {
	RoundID     uuid.UUID `gorm:"type:uuid;primaryKey" json:"round_id"`
	OperationID uuid.UUID `gorm:"type:uuid;unique;not null" json:"operation_id"`
	RunID       string    `gorm:"not null" json:"run_id"`
	CandidateID string    `gorm:"not null" json:"candidate_id"`
	ConfirmedBy uuid.UUID `gorm:"type:uuid;not null" json:"confirmed_by"`
	ConfirmedAt time.Time `gorm:"not null" json:"confirmed_at"`
}

type ReopenOperation struct {
	OperationID   uuid.UUID `gorm:"type:uuid;primaryKey"`
	SourceRoundID uuid.UUID `gorm:"type:uuid;not null"`
	NewRoundID    uuid.UUID `gorm:"type:uuid;not null"`
}
