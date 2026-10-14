package integration

import (
	"encoding/json"
	"github.com/google/uuid"
	"gorm.io/gorm/clause"
	"net/http"
	"planning-service/app/internal/model"
)

func (h *Handler) Preview(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	var body struct {
		ExpectedRevision *int `json:"expected_revision"`
		Retry            bool `json:"retry"`
	}
	if decode(w, r, &body) != nil || body.ExpectedRevision == nil || *body.ExpectedRevision < 0 {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	round, err := h.rounds.find(r.Context(), id)
	if err != nil || round.State != roundCollecting || !h.rounds.latestRound(r.Context(), round) {
		fail(w, 409, "COLLECTION_REQUIRED")
		return
	}
	memberID := currentUser(r)
	snapshot, err := h.call(r.Context(), h.participation, "GET", "/internal/rounds/"+id.String()+"/members/"+memberID.String()+"/preview-snapshot", nil)
	if err != nil {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	revision, ok := snapshot["response_revision"].(float64)
	if !ok || int(revision) != *body.ExpectedRevision {
		fail(w, 409, "STALE_VERSION")
		return
	}
	var definition map[string]any
	if json.Unmarshal(round.Definition, &definition) != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	definition["roster"] = []string{memberID.String()}
	run, err := h.call(r.Context(), h.decision, "POST", "/internal/previews", map[string]any{"planning": definition, "responses": snapshot, "retry": body.Retry})
	if err != nil {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	runID, ok := run["run_id"].(string)
	if !ok {
		fail(w, 503, "INVALID_UPSTREAM_RESPONSE")
		return
	}
	if _, err := uuid.Parse(runID); err != nil {
		fail(w, 503, "INVALID_UPSTREAM_RESPONSE")
		return
	}
	record := model.RoundPreview{RoundID: id, MemberID: memberID, RunID: runID, ResponseRevision: *body.ExpectedRevision}
	if err := h.db.WithContext(r.Context()).Clauses(clause.OnConflict{
		Columns:   []clause.Column{{Name: "round_id"}, {Name: "member_id"}},
		DoUpdates: clause.AssignmentColumns([]string{"run_id", "response_revision"}),
		Where:     clause.Where{Exprs: []clause.Expression{clause.Expr{SQL: "round_previews.response_revision <= EXCLUDED.response_revision"}}},
	}).Create(&record).Error; err != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	run["response_revision"] = *body.ExpectedRevision
	respondRun(w, run)
}

func (h *Handler) GetPreview(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	var record model.RoundPreview
	if h.db.WithContext(r.Context()).First(&record, "round_id = ? AND member_id = ?", id, currentUser(r)).Error != nil {
		fail(w, 404, "NOT_FOUND")
		return
	}
	snapshot, err := h.call(r.Context(), h.participation, "GET", "/internal/rounds/"+id.String()+"/members/"+currentUser(r).String()+"/preview-snapshot", nil)
	if err != nil {
		fail(w, 409, "COLLECTION_REQUIRED")
		return
	}
	if snapshot["response_revision"] != float64(record.ResponseRevision) {
		fail(w, 409, "STALE_VERSION")
		return
	}
	review, err := h.call(r.Context(), h.decision, "GET", "/internal/runs/"+record.RunID+"/clarifications/"+currentUser(r).String(), nil)
	if err != nil {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	review["response_revision"] = record.ResponseRevision
	respondRun(w, review)
}

func (h *Handler) Readiness(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	round, err := h.rounds.find(r.Context(), id)
	if err != nil {
		fail(w, 404, "NOT_FOUND")
		return
	}
	progress, err := h.call(r.Context(), h.participation, "GET", "/internal/rounds/"+id.String()+"/progress", nil)
	if err != nil {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	var definition map[string]any
	if json.Unmarshal(round.Definition, &definition) != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	check, err := h.call(r.Context(), h.decision, "POST", "/internal/planning/validate", definition)
	if err != nil {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	var count int64
	if h.db.Model(&model.PlanMember{}).Where("plan_id = ?", round.PlanID).Count(&count).Error != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	respond(w, 200, map[string]any{"round_id": id, "state": round.State, "member_count": count, "progress": progress, "definition": check})
}
