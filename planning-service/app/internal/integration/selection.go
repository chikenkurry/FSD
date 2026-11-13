package integration

import (
	"encoding/json"
	"errors"
	"gorm.io/gorm"
	"net/http"
	"planning-service/app/internal/httpapi"
	"planning-service/app/internal/model"
	"regexp"
	"time"

	"github.com/google/uuid"
)

type confirmationRequest struct {
	OperationID uuid.UUID `json:"operation_id"`
	RunID       string    `json:"run_id"`
	CandidateID string    `json:"candidate_id"`
	// Optional when the group voted on dates: the chosen day and local start time.
	EventDate string `json:"event_date,omitempty"`
	EventTime string `json:"event_time,omitempty"`
}

var (
	eventDatePattern = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)
	eventTimePattern = regexp.MustCompile(`^([01]\d|2[0-3]):[0-5]\d$`)
)

func validEventWhen(body confirmationRequest) bool {
	if body.EventDate == "" {
		return body.EventTime == ""
	}
	if !eventDatePattern.MatchString(body.EventDate) {
		return false
	}
	if _, err := time.Parse("2006-01-02", body.EventDate); err != nil {
		return false
	}
	return body.EventTime == "" || eventTimePattern.MatchString(body.EventTime)
}

func (h *Handler) Confirm(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	var body confirmationRequest
	if decode(w, r, &body) != nil || body.OperationID == uuid.Nil || body.CandidateID == "" || !validEventWhen(body) {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	runID, err := uuid.Parse(body.RunID)
	if err != nil || runID.String() != body.RunID {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	round, err := h.rounds.find(r.Context(), id)
	if err != nil {
		fail(w, 404, "NOT_FOUND")
		return
	}
	prior, err := h.rounds.findSelection(r.Context(), id)
	if err == nil {
		if !selectionMatches(prior, body) {
			fail(w, 409, "OPERATION_CONFLICT")
			return
		}
		respond(w, 200, prior)
		return
	}
	if round.State != roundReview || round.LastRunID != body.RunID || !h.rounds.latestRound(r.Context(), round) {
		fail(w, 409, "STALE_RESULT")
		return
	}
	payload := map[string]any{"input_refs": refs(round), "candidate_id": body.CandidateID}
	validated, err := h.call(r.Context(), h.decision, "POST", "/internal/runs/"+body.RunID+"/validate-selection", payload)
	if err != nil {
		if remote, ok := err.(RemoteError); !ok || remote.Status >= 500 {
			fail(w, 503, "UPSTREAM_UNAVAILABLE")
			return
		}
		fail(w, 409, "INELIGIBLE_RESULT")
		return
	}
	details, ok := validated["selected_details"].(map[string]any)
	if !ok {
		fail(w, 503, "INVALID_UPSTREAM_RESPONSE")
		return
	}
	var definition map[string]any
	if json.Unmarshal(round.EvaluationSnapshot(), &definition) != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	for _, key := range []string{"currency", "currency_minor_digits", "cost_scope", "timezone", "execution_mode"} {
		details[key] = definition[key]
	}
	if body.EventDate != "" {
		details["event_date"] = body.EventDate
		if body.EventTime != "" {
			details["event_time"] = body.EventTime
		}
	}
	selection, err := h.rounds.confirm(r.Context(), round, body, currentUser(r), encoded(details))
	if err != nil {
		fail(w, 409, "CONFIRMATION_CONFLICT")
		return
	}
	respond(w, 200, selection)
}

// Compatibility route reads the authoritative selection rather than the retired write table.
func (h *Handler) GetPlanSelection(w http.ResponseWriter, r *http.Request) {
	id, ok := httpapi.PathUUID(w, r, "plan_id", "INVALID_INPUT")
	if !ok {
		return
	}
	var selection Selection
	err := h.db.WithContext(r.Context()).Where("plan_id = ?", id).Order("version DESC").First(&selection).Error
	if err == nil {
		respond(w, 200, selection)
		return
	}
	if !errors.Is(err, gorm.ErrRecordNotFound) {
		fail(w, 500, "INTERNAL")
		return
	}
	var legacy model.ConfirmedSelection
	if h.db.WithContext(r.Context()).Where("plan_id = ?", id).First(&legacy).Error != nil {
		fail(w, 404, "NOT_FOUND")
		return
	}
	respond(w, 200, legacy)
}

func (h *Handler) GetSelection(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	selection, err := h.rounds.findSelection(r.Context(), id)
	if err != nil {
		fail(w, 404, "NOT_FOUND")
		return
	}
	respond(w, 200, selection)
}

func (h *Handler) SelectionContext(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	round, err := h.rounds.find(r.Context(), id)
	if err != nil {
		fail(w, 404, "NOT_FOUND")
		return
	}
	selection, err := h.rounds.findSelection(r.Context(), id)
	if err != nil {
		fail(w, 404, "NOT_FOUND")
		return
	}
	respond(w, 200, map[string]any{"plan_id": round.PlanID, "round_id": id, "selection_version": selection.Version,
		"is_current": round.State == roundConfirmed && h.rounds.latestRound(r.Context(), round)})
}

func (h *Handler) Reopen(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	var body struct {
		OperationID uuid.UUID `json:"operation_id"`
	}
	if decode(w, r, &body) != nil || body.OperationID == uuid.Nil {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	created, err := h.rounds.reopen(r.Context(), id, body.OperationID)
	if err != nil {
		fail(w, 409, "REOPEN_CONFLICT")
		return
	}
	respond(w, 200, created)
}
