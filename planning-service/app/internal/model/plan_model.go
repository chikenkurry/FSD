package model

import (
	"time"

	"github.com/google/uuid"
)

type PlanState string

const (
	PlanStateDraft      PlanState = "draft"
	PlanStateCollecting PlanState = "collecting"
	PlanStateReviewing  PlanState = "reviewing"
	PlanStateConfirmed  PlanState = "confirmed"
	PlanStateArchived   PlanState = "archived"
)

type PlanCategory string

const (
	CategoryMeeting PlanCategory = "MEETING"
	CategoryTravel  PlanCategory = "TRAVEL"
	CategoryDining  PlanCategory = "DINING"
	CategoryGeneral PlanCategory = "GENERAL"
)

func (c PlanCategory) IsValidCategory() bool {
	switch c {
		case CategoryMeeting, CategoryTravel, CategoryDining, CategoryGeneral:
			return true
	}
	return false
}

type Plan struct {
	ID              uuid.UUID    `gorm:"type:uuid;default:gen_random_uuid();primaryKey" json:"id"`
	Title           string       `gorm:"type:varchar(255);not null" json:"title"`
	Description     *string      `gorm:"type:text" json:"description,omitempty"`
	Category        PlanCategory `gorm:"type:varchar(50);not null;" json:"category"`
	Status          PlanState    `gorm:"type:varchar(50);default:'DRAFT';not null;index:idx_plans_status" json:"status"`
	CreatedByUserID uuid.UUID    `gorm:"type:uuid;not null;index:idx_plans_created_by" json:"created_by_user_id"`
	TimeWindowStart *time.Time   `gorm:"type:timestamptz" json:"time_window_start,omitempty"`
	TimeWindowEnd   *time.Time   `gorm:"type:timestamptz" json:"time_window_end,omitempty"`
	CreatedAt       time.Time    `gorm:"type:timestamptz;not null;default:CURRENT_TIMESTAMP" json:"created_at"`
	UpdatedAt       time.Time    `gorm:"type:timestamptz;not null;default:CURRENT_TIMESTAMP" json:"updated_at"`

	// Relationships
	CreatedBy          User                `gorm:"foreignKey:CreatedByUserID;constraint:OnDelete:RESTRICT" json:"created_by,omitempty"`
	Rounds             []PlanRound         `gorm:"foreignKey:PlanID;constraint:OnDelete:CASCADE" json:"rounds,omitempty"`
	Members            []PlanMember        `gorm:"foreignKey:PlanID;constraint:OnDelete:CASCADE" json:"members,omitempty"`
	ProposedActivities []ProposedActivity  `gorm:"foreignKey:PlanID;constraint:OnDelete:CASCADE" json:"proposed_activities,omitempty"`
	ConfirmedSelection *ConfirmedSelection `gorm:"foreignKey:PlanID;constraint:OnDelete:CASCADE" json:"confirmed_selection,omitempty"`
}

func (Plan) TableName() string {
	return "plans"
}
