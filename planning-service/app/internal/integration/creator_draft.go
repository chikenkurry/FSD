package integration

import (
	"encoding/json"
	"net/http"
	"planning-service/app/internal/database"
	"planning-service/app/internal/model"
)

// Store UI metadata only. The plan, options and questions remain authoritative.
type creatorState struct {
	Currency         string `json:"currency"`
	DecisionQuestion string `json:"decision_question"`
	Location         string `json:"location"`
	Step             int    `json:"step"`
	Visited          int    `json:"visited"`
}

func (h *Handler) SaveCreatorDraft(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	var state creatorState
	if decode(w, r, &state) != nil || state.Step < 1 || state.Step > 5 || state.Visited < state.Step || state.Visited > 5 ||
		len(state.Currency) != 3 || len(state.DecisionQuestion) > 1200 || len(state.Location) > 1000 {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	db := database.ContextDB(r.Context(), h.db)
	var round model.PlanRound
	if db.First(&round, "id = ?", id).Error != nil {
		fail(w, 404, "NOT_FOUND")
		return
	}
	latest, err := latestPlanRound(db, round.PlanID)
	if err != nil || latest.ID != id {
		fail(w, 409, "STALE_DRAFT")
		return
	}
	if err := db.Model(&round).Update("creator_state", encoded(state)).Error; err != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	respond(w, 200, state)
}

func (h *Handler) GetCreatorDraft(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	var round model.PlanRound
	if h.db.WithContext(r.Context()).First(&round, "id = ?", id).Error != nil {
		fail(w, 404, "NOT_FOUND")
		return
	}
	var published int64
	if h.db.Model(&Round{}).Where("id = ?", id).Count(&published).Error != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	if published > 0 {
		fail(w, 409, "REOPEN_REQUIRED")
		return
	}
	state := json.RawMessage(round.CreatorState)
	if len(state) == 0 {
		state = json.RawMessage(`{}`)
	}
	respond(w, 200, map[string]any{"round": round, "state": state})
}
