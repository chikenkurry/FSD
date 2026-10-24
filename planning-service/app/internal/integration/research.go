package integration

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strings"
	"time"

	"planning-service/app/internal/httpapi"
	"planning-service/app/internal/model"

	"github.com/google/uuid"
)

var (
	placeID   = regexp.MustCompile(`^[A-Za-z0-9_-]{10,300}$`)
	photoName = regexp.MustCompile(`^places/([A-Za-z0-9_-]{10,300})/photos/([A-Za-z0-9_-]{10,1000})$`)
)

type researchRequest struct {
	Task  string         `json:"task"`
	Input map[string]any `json:"input"`
	Retry bool           `json:"retry"`
}

func roundPlan(r *http.Request) uuid.UUID {
	planID, _ := r.Context().Value(planKey{}).(uuid.UUID)
	return planID
}

// Research provides public overviews, question drafts and sourced option facts.
func (h *Handler) Research(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	var body researchRequest
	if decode(w, r, &body) != nil || body.Input == nil {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	planID := roundPlan(r)
	var published Round
	if h.db.WithContext(r.Context()).First(&published, "id = ?", id).Error == nil {
		// A published round's facts are frozen. Before confirming, the organiser
		// may re-check them; the result is advisory and never changes the round.
		if body.Task != "facts" || published.State != roundReview || !h.rounds.latestRound(r.Context(), published) {
			fail(w, 409, "FROZEN_HISTORY")
			return
		}
	}
	run, err := h.call(r.Context(), h.decision, "POST", "/internal/research", map[string]any{
		"task": body.Task, "input": body.Input, "retry": body.Retry,
		"refs": map[string]any{"plan_id": planID.String(), "round_id": id.String()}})
	if err != nil {
		var remote RemoteError
		if errors.As(err, &remote) {
			fail(w, remote.Status, remote.Code)
			return
		}
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	respondRun(w, run)
}

func (h *Handler) GetResearch(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	planID := roundPlan(r)
	if !h.member(currentUser(r), planID, true) {
		fail(w, 403, "FORBIDDEN")
		return
	}
	runID, err := uuid.Parse(r.URL.Query().Get("run"))
	if err != nil {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	run, err := h.call(r.Context(), h.decision, "GET", "/internal/runs/"+runID.String(), nil)
	if err != nil {
		fail(w, 404, "NOT_FOUND")
		return
	}
	// A run is only readable through the round it was requested for.
	refs, _ := run["input_refs"].(map[string]any)
	if refs == nil || refs["plan_id"] != planID.String() || refs["round_id"] != id.String() {
		fail(w, 404, "NOT_FOUND")
		return
	}
	respondRun(w, run)
}

// Place content is fetched live for display; only place IDs are stored, on options of this plan.
func (h *Handler) planHasPlace(ctx context.Context, planID uuid.UUID, place string) bool {
	var count int64
	h.db.WithContext(ctx).Model(&model.ProposedActivity{}).
		Where("plan_id = ? AND metadata->'identity'->>'place_id' = ?", planID, place).Count(&count)
	return count > 0
}

func (h *Handler) Place(w http.ResponseWriter, r *http.Request) {
	if _, ok := rowID(w, r); !ok {
		return
	}
	place := r.URL.Query().Get("place_id")
	if !placeID.MatchString(place) || !h.planHasPlace(r.Context(), roundPlan(r), place) {
		fail(w, 404, "NOT_FOUND")
		return
	}
	card, err := h.call(r.Context(), h.decision, "GET", "/internal/places/"+place, nil)
	if err != nil {
		var remote RemoteError
		if errors.As(err, &remote) {
			fail(w, remote.Status, remote.Code)
			return
		}
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	w.Header().Set("Cache-Control", "private, max-age=300")
	respond(w, 200, card)
}

func (h *Handler) PlacePhoto(w http.ResponseWriter, r *http.Request) {
	if _, ok := rowID(w, r); !ok {
		return
	}
	parts := photoName.FindStringSubmatch(r.URL.Query().Get("name"))
	if parts == nil || !h.planHasPlace(r.Context(), roundPlan(r), parts[1]) {
		fail(w, 404, "NOT_FOUND")
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 12*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, "GET", strings.TrimRight(h.decision, "/")+fmt.Sprintf("/internal/places/%s/photos/%s", parts[1], parts[2]), nil)
	if err != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	req.Header.Set("x-internal-token", h.token)
	req.Header.Set("x-request-id", httpapi.RequestID(r.Context()))
	response, err := http.DefaultClient.Do(req)
	if err != nil {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	defer response.Body.Close()
	kind := response.Header.Get("Content-Type")
	if response.StatusCode != 200 || !strings.HasPrefix(kind, "image/") {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	w.Header().Set("Content-Type", kind)
	w.Header().Set("Cache-Control", "private, max-age=3600")
	w.WriteHeader(200)
	io.Copy(w, io.LimitReader(response.Body, 8_000_000))
}
