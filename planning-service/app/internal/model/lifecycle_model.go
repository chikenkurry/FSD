package model

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

type PublishedRound struct {
	RosterPolicy         string         `gorm:"not null;default:publication" json:"roster_policy"`
	EvaluationDefinition datatypes.JSON `gorm:"type:jsonb" json:"-"`
	ID                   uuid.UUID      `gorm:"type:uuid;primaryKey" json:"round_id"`
	PlanID               uuid.UUID      `gorm:"type:uuid;not null;index" json:"plan_id"`
	State                string         `gorm:"not null" json:"state"`
	OptionRevision       int            `gorm:"not null" json:"option_revision"`
	OptionSnapshotID     uuid.UUID      `gorm:"type:uuid;not null" json:"option_snapshot_id"`
	Definition           datatypes.JSON `gorm:"type:jsonb;not null" json:"-"`
	Settings             datatypes.JSON `gorm:"type:jsonb;not null" json:"-"`
	PublishOperationID   uuid.UUID      `gorm:"type:uuid;not null" json:"-"`
	FreezeOperationID    uuid.UUID      `gorm:"type:uuid;not null" json:"-"`
	ResponseSnapshotID   string         `json:"response_snapshot_id,omitempty"`
	LastRunID            string         `json:"recommendation_run_id,omitempty"`
}

func (PublishedRound) TableName() string { return "integration_rounds" }

type RoundSelection struct {
	PlanID             uuid.UUID      `gorm:"type:uuid;index" json:"plan_id"`
	Version            int            `gorm:"not null;default:1" json:"selection_version"`
	OptionSnapshotID   uuid.UUID      `gorm:"type:uuid" json:"option_snapshot_id"`
	ResponseSnapshotID string         `json:"response_snapshot_id"`
	Details            datatypes.JSON `gorm:"type:jsonb" json:"selected_details"`
	RoundID            uuid.UUID      `gorm:"type:uuid;primaryKey" json:"round_id"`
	OperationID        uuid.UUID      `gorm:"type:uuid;unique;not null" json:"operation_id"`
	RunID              string         `gorm:"not null" json:"run_id"`
	CandidateID        string         `gorm:"not null" json:"candidate_id"`
	ConfirmedBy        uuid.UUID      `gorm:"type:uuid;not null" json:"confirmed_by"`
	ConfirmedAt        time.Time      `gorm:"not null" json:"confirmed_at"`
}

type ReopenOperation struct {
	OperationID   uuid.UUID `gorm:"type:uuid;primaryKey"`
	SourceRoundID uuid.UUID `gorm:"type:uuid;not null"`
	NewRoundID    uuid.UUID `gorm:"type:uuid;not null"`
}

func (RoundSelection) TableName() string { return "selections" }

type RoundPreview struct {
	RoundID          uuid.UUID `gorm:"type:uuid;primaryKey"`
	MemberID         uuid.UUID `gorm:"type:uuid;primaryKey"`
	RunID            string    `gorm:"not null"`
	ResponseRevision int       `gorm:"not null"`
}

type FactCollectionRef struct {
	RoundID uuid.UUID `gorm:"type:uuid;primaryKey"`
	RunID   string    `gorm:"not null"`
}

type FactAcceptance struct {
	OperationID     uuid.UUID `gorm:"type:uuid;primaryKey" json:"operation_id"`
	TargetRoundID   uuid.UUID `gorm:"type:uuid;not null" json:"target_round_id"`
	PayloadHash     string    `gorm:"not null" json:"-"`
	CollectionRunID string    `gorm:"not null" json:"collection_run_id"`
	ReviewedBy      uuid.UUID `gorm:"type:uuid;not null" json:"reviewed_by"`
	AppliedAt       time.Time `gorm:"not null" json:"applied_at"`
}

// PlanRound owns draft metadata; PublishedRound is the sole lifecycle authority.
func (r PublishedRound) EvaluationSnapshot() datatypes.JSON {
	if len(r.EvaluationDefinition) > 0 {
		return r.EvaluationDefinition
	}
	return r.Definition
}
