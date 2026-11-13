package integration

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"planning-service/app/internal/httpapi"

	"github.com/google/uuid"
)

func validateMutationBody(w http.ResponseWriter, r *http.Request, parts []string, user uuid.UUID) (uuid.UUID, bool) {
	if len(parts) < 2 {
		fail(w, 400, "INVALID_INPUT")
		return uuid.Nil, false
	}
	var bodyPlanID uuid.UUID
	payload, err := io.ReadAll(http.MaxBytesReader(w, r.Body, httpapi.MaxBodyBytes))
	if err != nil {
		fail(w, 413, "INVALID_INPUT")
		return uuid.Nil, false
	}
	r.Body = io.NopCloser(bytes.NewReader(payload))
	body := map[string]any{}
	if len(payload) > 0 && json.Unmarshal(payload, &body) != nil {
		fail(w, 400, "INVALID_INPUT")
		return uuid.Nil, false
	}
	if claimed, ok := body["plan_id"].(string); ok {
		bodyPlanID, _ = uuid.Parse(claimed)
	}
	for _, key := range []string{"organiser_id", "user_id", "created_by", "confirmed_by_user_id"} {
		if claimed, ok := body[key].(string); ok && claimed != user.String() {
			fail(w, 403, "FORBIDDEN")
			return uuid.Nil, false
		}
	}
	if parts[1] == "confirmed-selection" || (parts[1] == "plans" && body["state"] != nil) || (parts[1] == "rounds" && body["is_active"] != nil) {
		fail(w, 409, "USE_ROUND_LIFECYCLE")
		return uuid.Nil, false
	}
	return bodyPlanID, true
}

func (h *Handler) allowPlanMutation(w http.ResponseWriter, r *http.Request, parts []string, planID uuid.UUID) bool {
	if editsDefinition(parts) {
		latest, err := latestPlanRound(h.db, planID)
		if err == nil {
			var frozen Round
			if h.db.First(&frozen, "id = ?", latest.ID).Error == nil && frozen.State != "DRAFT" {
				rosterEdit := parts[1] == "members" || (parts[1] == "plans" && len(parts) > 3 && parts[3] == "members")
				if rosterEdit && frozen.State == roundCollecting && frozen.RosterPolicy == "close" {
					return true
				}
				fail(w, 409, "REOPEN_REQUIRED")
				return false
			}
		}
	}
	var frozen Round
	if r.Method == "DELETE" && ((parts[1] == "rounds" && h.db.First(&frozen, "id = ?", parts[len(parts)-1]).Error == nil) ||
		(parts[1] == "plans" && len(parts) == 3 && h.db.Where("plan_id = ?", planID).First(&frozen).Error == nil)) {
		fail(w, 409, "FROZEN_HISTORY")
		return false
	}
	if parts[1] == "rounds" && len(parts) == 4 && parts[2] == "plans" && r.Method == "POST" {
		var count int64
		h.db.Model(&Round{}).Where("plan_id = ? AND state IN ?", planID, []string{roundPublishing, roundCollecting, roundLocking}).Count(&count)
		if count > 0 {
			fail(w, 409, "CLOSE_ROUND_FIRST")
			return false
		}
	}
	return true
}

func (h *Handler) planForPath(parts []string, user uuid.UUID) (uuid.UUID, bool) {
	if len(parts) < 2 {
		return uuid.Nil, false
	}
	resource := parts[1]
	if resource == "session" {
		return uuid.Nil, true
	}
	if resource == "users" {
		if len(parts) == 2 {
			return uuid.Nil, true
		}
		id, err := uuid.Parse(parts[2])
		return uuid.Nil, err == nil && id == user
	}
	if resource == "invites" {
		return uuid.Nil, true
	}
	if resource == "plans" && len(parts) == 2 {
		return uuid.Nil, true
	}
	if resource == "plans" && len(parts) > 3 && (parts[2] == "organiser" || parts[2] == "member") {
		id, err := uuid.Parse(parts[3])
		return uuid.Nil, err == nil && id == user
	}
	for i, part := range parts {
		if (part == "plans" || part == "plan_members") && i+1 < len(parts) {
			if id, err := uuid.Parse(parts[i+1]); err == nil {
				return id, true
			}
			if (parts[i+1] == "details" || parts[i+1] == "question") && i+2 < len(parts) {
				id, err := uuid.Parse(parts[i+2])
				return id, err == nil
			}
		}
	}
	index := 2
	if resource == "rounds" && len(parts) > 2 && parts[2] == "open" {
		index = 3
	}
	if len(parts) <= index {
		return uuid.Nil, false
	}
	id, err := uuid.Parse(parts[index])
	if err != nil {
		return uuid.Nil, false
	}
	tables := map[string]string{"rounds": "plan_rounds", "proposed_activity": "proposed_activities", "question": "questions", "members": "plan_members"}
	table, ok := tables[resource]
	if !ok {
		return uuid.Nil, false
	}
	var result struct{ PlanID uuid.UUID }
	err = h.db.Table(table).Select("plan_id").Where("id = ?", id).Take(&result).Error
	return result.PlanID, err == nil
}

func editsDefinition(parts []string) bool {
	resource := parts[1]
	return resource == "question" || resource == "proposed_activity" || resource == "members" ||
		(resource == "plans" && len(parts) == 3) ||
		(resource == "plans" && len(parts) > 3 && parts[3] == "members")
}
