package model

import (
	"time"

	"github.com/google/uuid"
	"gorm.io/datatypes"
)

type QuestionType string

const (
	QuestionTypeTitle        QuestionType = "TITLE"
	QuestionTypeDescription  QuestionType = "DESCRIPTION"
	QuestionTypeActivityType QuestionType = "ACTIVITY_TYPE"
	QuestionTypeMeetingDate  QuestionType = "MEETING_DATE"
	QuestionTypeMeetingTime  QuestionType = "MEETING_TIME"
	QuestionTypeDuration     QuestionType = "DURATION"
	QuestionTypeLocation     QuestionType = "LOCATION"
	QuestionTypeBudget       QuestionType = "BUDGET"

	QuestionTypeCustomText         QuestionType = "CUSTOM_TEXT"
	QuestionTypeCustomSingleChoice QuestionType = "CUSTOM_SINGLE_CHOICE"
	QuestionTypeCustomMultiChoice  QuestionType = "CUSTOM_MULTI_CHOICE"
)

type Question struct {
	ID          uuid.UUID    `gorm:"type:uuid;primaryKey;default:gen_random_uuid()" json:"id"`
	PlanID      uuid.UUID    `gorm:"type:uuid;not null;index" json:"plan_id"`
	Title       string       `gorm:"type:varchar(255);not null" json:"title"` // The label shown to users (e.g. "Where should we meet?")
	Type        QuestionType `gorm:"type:varchar(50);not null" json:"type"`   // Standard or Custom type
	Description *string      `gorm:"type:text" json:"description,omitempty"`  // Optional help text
	IsRequired  bool         `gorm:"type:boolean;default:false;not null" json:"is_required"`
	SortOrder   int          `gorm:"type:integer;default:0;not null" json:"sort_order"` // For reordering questions on the form

	// Options stores unstructured metadata for custom choices, range limits, or default values as JSON
	// e.g. {"options": ["Italian", "Japanese", "Mexican"], "allow_other": true}
	Options datatypes.JSON `gorm:"type:jsonb" json:"options,omitempty"`

	CreatedAt time.Time `gorm:"autoCreateTime" json:"created_at"`
	UpdatedAt time.Time `gorm:"autoUpdateTime" json:"updated_at"`

	// Relations
	Plan *Plan `gorm:"foreignKey:PlanID;references:ID;constraint:OnDelete:CASCADE" json:"-"`
}

type QuestionPreset struct {
	ID          uuid.UUID      `gorm:"type:uuid;primaryKey;default:gen_random_uuid()" json:"id"`
	Category    PlanCategory   `gorm:"type:varchar(50);not null;" json:"category"`
	Title       string         `gorm:"type:varchar(255);not null" json:"title"` // e.g. "Locations to visit"
	Type        QuestionType   `gorm:"type:varchar(50);not null" json:"type"`   // e.g. "LOCATION", "BUDGET"
	Description string         `gorm:"type:text" json:"description,omitempty"`
	IsRequired  bool           `gorm:"type:boolean;default:false" json:"is_required"`
	SortOrder   int            `gorm:"type:integer;default:0" json:"sort_order"`
	Options     datatypes.JSON `gorm:"type:jsonb" json:"options,omitempty"`
}
