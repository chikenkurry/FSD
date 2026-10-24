package model

import (
	"time"

	"github.com/google/uuid"
	"gorm.io/datatypes"
)

type PlanRound struct {
	ID            uuid.UUID      `gorm:"type:uuid;default:gen_random_uuid();primaryKey" json:"id"`
	PlanID        uuid.UUID      `gorm:"type:uuid;not null;uniqueIndex:uq_plan_round,priority:1;index:idx_plan_rounds_active,where:is_active = true" json:"plan_id"`
	RoundNumber   int            `gorm:"type:int;not null;default:1;uniqueIndex:uq_plan_round,priority:2" json:"round_number"`
	DeadlineAt    *time.Time     `gorm:"type:timestamptz" json:"deadline_at,omitempty"`
	IsActive      bool           `gorm:"type:boolean;not null;default:false" json:"is_active"`
	CreatedAt     time.Time      `gorm:"type:timestamptz;not null;default:CURRENT_TIMESTAMP" json:"created_at"`
	CreatorState  datatypes.JSON `gorm:"type:jsonb" json:"creator_state,omitempty"`
	SourceRoundID *uuid.UUID     `gorm:"type:uuid" json:"source_round_id,omitempty"`
}

func (PlanRound) TableName() string {
	return "plan_rounds"
}
