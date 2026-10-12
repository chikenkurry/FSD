package model

import (
	"github.com/google/uuid"
)

type User struct {
	ID       uuid.UUID `gorm:"type:uuid;default:gen_random_uuid();primaryKey" json:"id"`
	Username string    `gorm:"type:varchar(255);not null" json:"username"`

	// Relationships
	CreatedPlans []Plan       `gorm:"foreignKey:CreatedByUserID" json:"created_plans,omitempty"`
	Memberships  []PlanMember `gorm:"foreignKey:UserID" json:"memberships,omitempty"`
}

func (User) TableName() string {
	return "users"
}