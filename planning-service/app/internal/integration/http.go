package integration

import (
	"encoding/json"
	"net/http"

	"github.com/google/uuid"
	"gorm.io/datatypes"
)

func respond(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(body)
}
func fail(w http.ResponseWriter, status int, code string) {
	respond(w, status, map[string]any{"code": code})
}
func decode(w http.ResponseWriter, r *http.Request, value any) error {
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 2_000_000))
	decoder.DisallowUnknownFields()
	return decoder.Decode(value)
}
func rowID(w http.ResponseWriter, r *http.Request) (uuid.UUID, bool) {
	id, err := uuid.Parse(r.PathValue("id"))
	if err != nil {
		fail(w, 400, "INVALID_INPUT")
	}
	return id, err == nil
}
func encoded(value any) datatypes.JSON { data, _ := json.Marshal(value); return data }
func refs(round Round) map[string]any {
	return map[string]any{"plan_id": round.PlanID.String(), "round_id": round.ID.String(), "option_revision": round.OptionRevision, "option_snapshot_id": round.OptionSnapshotID.String(), "response_snapshot_id": round.ResponseSnapshotID}
}
