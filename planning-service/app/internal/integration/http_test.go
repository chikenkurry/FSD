package integration

import (
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

// The integration shorthands keep their own contract on top of httpapi: the
// error code doubles as the message, and request bodies are strict.

func TestFailUsesTheCodeAsTheMessage(t *testing.T) {
	rec := httptest.NewRecorder()
	fail(rec, 409, "REOPEN_REQUIRED")
	var body struct{ Code, Message string }
	json.Unmarshal(rec.Body.Bytes(), &body)
	if rec.Code != 409 || body.Code != "REOPEN_REQUIRED" || body.Message != "REOPEN_REQUIRED" {
		t.Fatalf("unexpected error: %d %s", rec.Code, rec.Body.String())
	}
}

func TestDecodeRejectsUnknownFields(t *testing.T) {
	var body struct {
		Retry bool `json:"retry"`
	}
	req := httptest.NewRequest("POST", "/", strings.NewReader(`{"retry":true,"surprise":1}`))
	if decode(httptest.NewRecorder(), req, &body) == nil {
		t.Fatal("integration decode accepted an unknown field")
	}
}

func TestRowID(t *testing.T) {
	id := uuid.New()
	req := httptest.NewRequest("GET", "/", nil)
	req.SetPathValue("id", id.String())
	if got, ok := rowID(httptest.NewRecorder(), req); !ok || got != id {
		t.Fatal("valid round id rejected")
	}

	req = httptest.NewRequest("GET", "/", nil)
	req.SetPathValue("id", "nope")
	rec := httptest.NewRecorder()
	if _, ok := rowID(rec, req); ok || rec.Code != 400 || !strings.Contains(rec.Body.String(), `"code":"INVALID_INPUT","message":"INVALID_INPUT"`) {
		t.Fatalf("bad id: ok=%v %d %s", ok, rec.Code, rec.Body.String())
	}
}