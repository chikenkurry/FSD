package integration

import (
	"encoding/json"
	"net/http"
	"planning-service/app/internal/httpapi"

	"github.com/google/uuid"
	"gorm.io/datatypes"
)

// Package shorthands over the shared httpapi helpers. Integration endpoints use
// the error code as the message and reject unknown request fields.

func respond(w http.ResponseWriter, status int, body any) { httpapi.JSON(w, status, body) }
func fail(w http.ResponseWriter, status int, code string) { httpapi.Error(w, status, code, code) }
func respondRun(w http.ResponseWriter, run map[string]any) {
	status := 200
	if run["status"] == "pending" {
		status = 202
		w.Header().Set("Retry-After", "1")
	}
	respond(w, status, run)
}
func decode(w http.ResponseWriter, r *http.Request, value any) error {
	return httpapi.DecodeStrict(w, r, value)
}
func rowID(w http.ResponseWriter, r *http.Request) (uuid.UUID, bool) {
	return httpapi.PathUUID(w, r, "id", "INVALID_INPUT")
}
func encoded(value any) datatypes.JSON { data, _ := json.Marshal(value); return data }
func refs(round Round) map[string]any {
	return map[string]any{"plan_id": round.PlanID.String(), "round_id": round.ID.String(), "option_revision": round.OptionRevision, "option_snapshot_id": round.OptionSnapshotID.String(), "response_snapshot_id": round.ResponseSnapshotID}
}