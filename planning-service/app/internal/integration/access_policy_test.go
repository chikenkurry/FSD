package integration

import (
	"encoding/json"
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestMutationBodyRejectsAnotherUsersIdentity(t *testing.T) {
	user := uuid.New()
	for _, field := range []string{"organiser_id", "user_id", "created_by", "confirmed_by_user_id"} {
		t.Run(field, func(t *testing.T) {
			body, _ := json.Marshal(map[string]string{field: uuid.New().String()})
			req := httptest.NewRequest("POST", "/v1/plans", strings.NewReader(string(body)))
			res := httptest.NewRecorder()
			_, allowed := validateMutationBody(res, req, []string{"v1", "plans"}, user)
			if allowed || res.Code != 403 {
				t.Fatalf("identity impersonation returned allowed=%v, status=%d", allowed, res.Code)
			}
		})
	}
}

func TestMutationBodyRequiresRoundLifecycleForStateChanges(t *testing.T) {
	cases := []struct {
		path string
		body map[string]any
	}{
		{"/v1/plans/" + uuid.New().String(), map[string]any{"state": "CONFIRMED"}},
		{"/v1/rounds/" + uuid.New().String(), map[string]any{"is_active": true}},
		{"/v1/confirmed-selection/plans/" + uuid.New().String(), map[string]any{}},
	}
	for _, test := range cases {
		t.Run(test.path, func(t *testing.T) {
			body, _ := json.Marshal(test.body)
			req := httptest.NewRequest("POST", test.path, strings.NewReader(string(body)))
			res := httptest.NewRecorder()
			_, allowed := validateMutationBody(res, req, strings.Split(strings.Trim(test.path, "/"), "/"), uuid.New())
			if allowed || res.Code != 409 {
				t.Fatalf("lifecycle bypass returned allowed=%v, status=%d", allowed, res.Code)
			}
		})
	}
}

func TestMutationBodyPreservesPayloadForTheController(t *testing.T) {
	user, plan := uuid.New(), uuid.New()
	body, _ := json.Marshal(map[string]string{"plan_id": plan.String(), "created_by": user.String(), "title": "A question"})
	req := httptest.NewRequest("POST", "/v1/question", strings.NewReader(string(body)))
	res := httptest.NewRecorder()
	planID, allowed := validateMutationBody(res, req, []string{"v1", "question"}, user)
	if !allowed || planID != plan {
		t.Fatal("valid question creation was rejected")
	}
	remaining, err := io.ReadAll(req.Body)
	if err != nil || string(remaining) != string(body) {
		t.Fatal("access checks consumed or changed the controller's payload")
	}
}
