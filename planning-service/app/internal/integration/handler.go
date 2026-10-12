package integration

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

type Handler struct {
	db                             *gorm.DB
	rounds                         *roundStore
	participation, decision, token string
}

func NewHandler(db *gorm.DB, participation, decision, token string) *Handler {
	return &Handler{db: db, rounds: &roundStore{db: db}, participation: participation, decision: decision, token: token}
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
	if round.State == roundCollecting {
		respond(w, 200, round)
		return
	}
	var definition map[string]any
	if json.Unmarshal(round.Definition, &definition) != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	if _, err = h.call(r.Context(), h.decision, "POST", "/internal/planning/validate", definition); err != nil {
		var remote RemoteError
		if errors.As(err, &remote) && remote.Status == 400 {
			h.rounds.abandonPublication(r.Context(), id)
			fail(w, 400, "INVALID_DEFINITION")
			return
		}
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	payload, err := ProvisionPayload(round)
	if err != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	if _, err = h.call(r.Context(), h.participation, "POST", "/internal/rounds/provision", payload); err != nil {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	round, err = h.rounds.finalizePublication(r.Context(), id)
	if err != nil {
		fail(w, 503, "RETRY_PUBLISH")
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
	if round.ResponseSnapshotID != "" {
		respond(w, 200, round)
		return
	}
	var snapshot struct {
		Roster []string `json:"roster"`
	}
	if json.Unmarshal(round.Definition, &snapshot) != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	payload := map[string]any{"operationId": round.FreezeOperationID.String(), "roundId": id.String(), "memberIds": snapshot.Roster}
	result, err := h.call(r.Context(), h.participation, "POST", "/internal/rounds/freeze", payload)
	if err != nil {
		fail(w, 503, "RETRY_FREEZE")
		return
	}
	snapshotID, ok := result["snapshotId"].(string)
	if !ok {
		fail(w, 503, "INVALID_UPSTREAM_RESPONSE")
		return
	}
	if _, err = uuid.Parse(snapshotID); err != nil {
		fail(w, 503, "INVALID_UPSTREAM_RESPONSE")
		return
	}
	round, err = h.rounds.finalizeFreeze(r.Context(), id, snapshotID)
	if err != nil {
		fail(w, 503, "RETRY_FREEZE")
		return
	}
	respond(w, 200, round)
}

func (h *Handler) Recommend(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	round, err := h.rounds.find(r.Context(), id)
	if err != nil || round.State != roundReview || !h.rounds.latestRound(r.Context(), round) {
		fail(w, 409, "REVIEW_REQUIRED")
		return
	}
	run, err := h.call(r.Context(), h.decision, "POST", "/internal/rounds/"+id.String()+"/recommendations", map[string]any{})
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
	respond(w, 200, run)
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
	respond(w, 200, result)
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
