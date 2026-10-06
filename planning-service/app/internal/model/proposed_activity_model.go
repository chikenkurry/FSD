package model

import (
	"time"

	"github.com/google/uuid"
)

type ProposedActivity struct {
	ID                uuid.UUID `gorm:"type:uuid;default:gen_random_uuid();primaryKey" json:"id"`
	PlanID            uuid.UUID `gorm:"type:uuid;not null;index:idx_proposed_activities_plan" json:"plan_id"`
	Title             string    `gorm:"type:varchar(255);not null" json:"title"`
	Description       *string   `gorm:"type:text" json:"description,omitempty"`
	EstCostPerPerson  float64   `gorm:"type:numeric(10,2);not null;default:0.00" json:"est_cost_per_person"`
	DurationMinutes   int       `gorm:"type:int;not null;default:60" json:"duration_minutes"`
	Metadata          []byte    `gorm:"type:jsonb;not null;default:'{}'" json:"metadata"`
	CreatedAt         time.Time `gorm:"type:timestamptz;not null;default:CURRENT_TIMESTAMP" json:"created_at"`
}

func (ProposedActivity) TableName() string {
	return "proposed_activities"
}