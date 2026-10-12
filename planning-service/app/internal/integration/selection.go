package integration

import (
	"net/http"

	"github.com/google/uuid"
)

type confirmationRequest struct {
	OperationID uuid.UUID `json:"operation_id"`
	RunID       string    `json:"run_id"`
	CandidateID string    `json:"candidate_id"`
}

func (h *Handler) Confirm(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	var body confirmationRequest
	if decode(w, r, &body) != nil || body.OperationID == uuid.Nil || body.CandidateID == "" {
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
		if !prior.matches(body) {
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
	if _, err := h.call(r.Context(), h.decision, "POST", "/internal/runs/"+body.RunID+"/validate-selection", payload); err != nil {
		if remote, ok := err.(RemoteError); !ok || remote.Status >= 500 {
			fail(w, 503, "UPSTREAM_UNAVAILABLE")
			return
		}
		fail(w, 409, "INELIGIBLE_RESULT")
		return
	}
	selection, err := h.rounds.confirm(r.Context(), round, body, currentUser(r))
	if err != nil {
		fail(w, 409, "CONFIRMATION_CONFLICT")
		return
	}
	respond(w, 200, selection)
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
