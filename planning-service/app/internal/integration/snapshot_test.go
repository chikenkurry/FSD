package integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
	"gorm.io/datatypes"
)

func TestSnapshotUsesEvidenceAndStableQuestionIdentity(t *testing.T) {
	plan := model.Plan{ID: uuid.New(), Title: "Choose a device", Members: []model.PlanMember{{UserID: uuid.New()}},
		ProposedActivities: []model.ProposedActivity{{ID: uuid.New(), Title: "Device A", Metadata: []byte(`{"facts":[{"criterion":"mass","value":1,"unit":"kg","status":"confirmed","source":"specification"}]}`)}},
		Questions:          []model.Question{{ID: uuid.New(), Title: "Preferred mass?", Type: model.QuestionTypeCustomText, IsRequired: true, Options: datatypes.JSON(`{"decision":{"answer_format":"number","numeric_intent":"minimize"}}`)}}}
	round := model.PlanRound{ID: uuid.New(), RoundNumber: 2}
	snapshot, err := BuildSnapshot(plan, round, uuid.New(), Settings{Currency: "SGD", CostScope: "per_person_total"})
	if err != nil {
		t.Fatal(err)
	}
	if snapshot["option_revision"] != 2 {
		t.Fatal("revision was not preserved")
	}
	if _, ok := snapshot["options"].([]map[string]any)[0]["brief"]; ok {
		t.Fatal("brief invented without metadata")
	}
	plan.ProposedActivities[0].Metadata = []byte(`{"facts":[],"brief":{"summary":"A light laptop."}}`)
	withBrief, err := BuildSnapshot(plan, round, uuid.New(), Settings{})
	if err != nil || withBrief["options"].([]map[string]any)[0]["brief"].(map[string]any)["summary"] != "A light laptop." {
		t.Fatal("option brief not published")
	}
	plan.ProposedActivities[0].Metadata = []byte(`{"facts":[{"criterion":"mass","value":1,"unit":"kg","status":"confirmed","source":"specification"}]}`)
	if snapshot["decision_question"] != "Choose a device" {
		t.Fatal("decision question should fall back to the plan title")
	}
	asked, err := BuildSnapshot(plan, round, uuid.New(), Settings{DecisionQuestion: "  Which device should the team buy?  "})
	if err != nil || asked["decision_question"] != "Which device should the team buy?" {
		t.Fatal("organiser decision question lost")
	}
	question := snapshot["questions"].([]map[string]any)[0]
	if question["question_id"] != plan.Questions[0].ID.String() || question["answer_format"] != "number" {
		t.Fatal("question mapping lost")
	}
	stored := Round{Definition: encoded(snapshot), ID: round.ID, PlanID: plan.ID, OptionRevision: 2, OptionSnapshotID: uuid.New(), PublishOperationID: uuid.New()}
	payload, err := ProvisionPayload(stored)
	if err != nil {
		t.Fatal(err)
	}
	if payload["optionRevision"] != 2 {
		t.Fatal("provision revision lost")
	}
	// Numeric zero on the old display-only cost column is not a sourced fact.
	plan.ProposedActivities[0].Metadata = []byte(`{}`)
	withoutCost, err := BuildSnapshot(plan, round, uuid.New(), Settings{})
	if err != nil {
		t.Fatal(err)
	}
	data, _ := json.Marshal(withoutCost["options"])
	var options []struct{ Facts []any }
	json.Unmarshal(data, &options)
	if len(options[0].Facts) != 0 {
		t.Fatal("invented facts from a display column")
	}
}

func TestSettingsComparisonSurvivesPostgresJSONKeyOrdering(t *testing.T) {
	if !sameJSON([]byte(`{"currency":"SGD","timezone":"UTC"}`), []byte(`{"timezone":"UTC","currency":"SGD"}`)) {
		t.Fatal("equivalent settings conflict")
	}
	if sameJSON([]byte(`{"currency":"SGD"}`), []byte(`{"currency":"USD"}`)) {
		t.Fatal("changed settings accepted")
	}
}

func TestInternalRoutesRejectMissingAndWrongCredentials(t *testing.T) {
	h := NewHandler(nil, "", "", "test-internal-token-long-enough")
	called := false
	guarded := h.Internal(func(w http.ResponseWriter, r *http.Request) { called = true; w.WriteHeader(204) })
	for _, token := range []string{"", "wrong"} {
		req := httptest.NewRequest("GET", "/internal/test", nil)
		req.Header.Set("x-internal-token", token)
		res := httptest.NewRecorder()
		guarded(res, req)
		if res.Code != 401 || called {
			t.Fatal("internal route accepted invalid credential")
		}
	}
	req := httptest.NewRequest("GET", "/internal/test", nil)
	req.Header.Set("x-internal-token", h.token)
	res := httptest.NewRecorder()
	guarded(res, req)
	if res.Code != 204 || !called {
		t.Fatal("valid caller rejected")
	}
}
