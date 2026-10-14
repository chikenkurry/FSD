package integration

import (
	"encoding/json"
	"errors"
	"net/http"

	"context"
	"github.com/google/uuid"
	"gorm.io/gorm"
	"time"
)

type Handler struct {
	db                             *gorm.DB
	rounds                         *roundStore
	participation, decision, token string
}

func NewHandler(db *gorm.DB, participation, decision, token string) *Handler {
	return &Handler{db: db, rounds: &roundStore{db: db}, participation: participation, decision: decision, token: token}
}

func (h *Handler) Ready(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	if h.db.WithContext(ctx).Exec("SELECT 1").Error != nil {
		fail(w, 503, "DATABASE_UNAVAILABLE")
		return
	}
	respond(w, 200, map[string]string{"status": "ok"})
}

func (h *Handler) Publish(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	var settings Settings
	if decode(w, r, &settings) != nil {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	round, err := h.rounds.preparePublication(r.Context(), id, settings)
	if err != nil {
		fail(w, 409, "PUBLISH_CONFLICT")
		return
	}
	round, err = h.completePublication(r.Context(), round)
	if err != nil {
		if errors.Is(err, errInvalidDefinition) {
			fail(w, 400, "INVALID_DEFINITION")
			return
		}
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	respond(w, 200, round)
}

func (h *Handler) Snapshot(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	round, err := h.rounds.find(r.Context(), id)
	if err != nil || round.State == roundPublishing {
		fail(w, 404, "NOT_FOUND")
		return
	}
	respond(w, 200, json.RawMessage(round.Definition))
}

func (h *Handler) OptionSnapshot(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	round, err := h.rounds.find(r.Context(), id)
	if err != nil || (round.State != roundLocking && round.State != roundReview && round.State != roundConfirmed) {
		fail(w, 409, "FREEZE_REQUIRED")
		return
	}
	respond(w, 200, json.RawMessage(round.EvaluationSnapshot()))
}

func (h *Handler) Close(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	round, err := h.rounds.beginFreeze(r.Context(), id)
	if err != nil {
		fail(w, 409, "ROUND_NOT_COLLECTING")
		return
	}
	round, err = h.completeFreeze(r.Context(), round)
	if err != nil {
		fail(w, 503, "RETRY_FREEZE")
		return
	}
	respond(w, 200, round)
}

func (h *Handler) Recommend(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Retry bool `json:"retry"`
	}
	if decode(w, r, &body) != nil {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	round, err := h.rounds.find(r.Context(), id)
	if err != nil || round.State != roundReview || !h.rounds.latestRound(r.Context(), round) {
		fail(w, 409, "REVIEW_REQUIRED")
		return
	}
	run, err := h.call(r.Context(), h.decision, "POST", "/internal/rounds/"+id.String()+"/recommendations", map[string]any{"retry": body.Retry})
	if err != nil {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	runID, ok := run["run_id"].(string)
	if !ok {
		fail(w, 503, "INVALID_UPSTREAM_RESPONSE")
		return
	}
	if _, err = uuid.Parse(runID); err != nil {
		fail(w, 503, "INVALID_UPSTREAM_RESPONSE")
		return
	}
	err = h.rounds.saveRecommendation(r.Context(), round, runID)
	if err != nil {
		fail(w, 409, "STALE_RESULT")
		return
	}
	respondRun(w, run)
}

func (h *Handler) Result(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	round, err := h.rounds.find(r.Context(), id)
	if err != nil || round.LastRunID == "" {
		fail(w, 404, "NOT_FOUND")
		return
	}
	result, err := h.call(r.Context(), h.decision, "GET", "/internal/runs/"+round.LastRunID, nil)
	if err != nil {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	respondRun(w, result)
}

func (h *Handler) Clarifications(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	round, err := h.rounds.find(r.Context(), id)
	if err != nil || round.LastRunID == "" {
		fail(w, 404, "NOT_FOUND")
		return
	}
	result, err := h.call(r.Context(), h.decision, "GET", "/internal/runs/"+round.LastRunID+"/clarifications/"+currentUser(r).String(), nil)
	if err != nil {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	respond(w, 200, result)
}
