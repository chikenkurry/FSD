package model

import (
	"time"

	"github.com/google/uuid"
)

type MemberRole string

const (
	MemberRoleOrganiser MemberRole = "ORGANISER"
	MemberRoleMember    MemberRole = "MEMBER"
)

type PlanMember struct {
	ID          uuid.UUID  `gorm:"type:uuid;default:gen_random_uuid();primaryKey" json:"id"`
	PlanID      uuid.UUID  `gorm:"type:uuid;not null;uniqueIndex:uq_plan_user,priority:1" json:"plan_id"`
	UserID      uuid.UUID  `gorm:"type:uuid;not null;uniqueIndex:uq_plan_user,priority:2;index:idx_plan_members_user" json:"user_id"`
	DisplayName string     `gorm:"type:varchar(100);not null" json:"display_name"`
	Role        MemberRole `gorm:"type:varchar(50);default:'MEMBER';not null" json:"role"`
	JoinedAt    time.Time  `gorm:"type:timestamptz;not null;default:CURRENT_TIMESTAMP" json:"joined_at"`

	User *User `gorm:"foreignKey:UserID;references:ID" json:"user,omitempty"`
}

func (PlanMember) TableName() string {
	return "plan_members"
}