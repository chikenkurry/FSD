package model

import (
	"time"

	"github.com/google/uuid"
)


type ConfirmedSelection struct {
	ID                   uuid.UUID         `gorm:"type:uuid;default:gen_random_uuid();primaryKey" json:"id"`
	PlanID               uuid.UUID         `gorm:"type:uuid;not null;unique" json:"plan_id"`
	RecommendationRunID  uuid.UUID         `gorm:"type:uuid;not null" json:"recommendation_run_id"`
	Version              int               `gorm:"type:int;not null;default:1" json:"version"`
	SelectedActivityID   *uuid.UUID        `gorm:"type:uuid" json:"selected_activity_id,omitempty"`
	SelectedStartTime    time.Time         `gorm:"type:timestamptz;not null" json:"selected_start_time"`
	SelectedEndTime      time.Time         `gorm:"type:timestamptz;not null" json:"selected_end_time"`
	FinalCostPerPerson   float64           `gorm:"type:numeric(10,2);not null" json:"final_cost_per_person"`
	SelectionDetails     []byte            `gorm:"type:jsonb;not null;default:'{}'" json:"selection_details"`
	ConfirmedByUserID    uuid.UUID         `gorm:"type:uuid;not null" json:"confirmed_by_user_id"`
	ConfirmedAt          time.Time         `gorm:"type:timestamptz;not null;default:CURRENT_TIMESTAMP" json:"confirmed_at"`

	// Relationships
	SelectedActivity *ProposedActivity `gorm:"foreignKey:SelectedActivityID;constraint:OnDelete:SET NULL" json:"selected_activity,omitempty"`
}

func (ConfirmedSelection) TableName() string {
	return "confirmed_selections"
}