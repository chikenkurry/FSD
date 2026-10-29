package httpapi

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"
)

type errorBody struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	Retryable bool   `json:"retryable"`
}

func decodeError(t *testing.T, rec *httptest.ResponseRecorder) errorBody {
	t.Helper()
	if ct := rec.Header().Get("Content-Type"); ct != "application/json" {
		t.Fatalf("Content-Type = %q, want application/json", ct)
	}
	var body errorBody
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("error body is not JSON: %s", rec.Body.String())
	}
	return body
}

func TestCodeForStatus(t *testing.T) {
	cases := map[int]string{
		400: "INVALID_INPUT", 401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED",
		409: "OPERATION_CONFLICT", 410: "EXPIRED", 429: "RATE_LIMITED", 500: "INTERNAL", 502: "INTERNAL", 418: "INTERNAL",
	}
	for status, want := range cases {
		if got := CodeForStatus(status); got != want {
			t.Errorf("CodeForStatus(%d) = %q, want %q", status, got, want)
		}
	}
}

func TestJSON(t *testing.T) {
	rec := httptest.NewRecorder()
	JSON(rec, http.StatusCreated, map[string]int{"n": 1})
	if rec.Code != http.StatusCreated || rec.Header().Get("Content-Type") != "application/json" || rec.Body.String() != "{\"n\":1}\n" {
		t.Fatalf("got %d %q %q", rec.Code, rec.Header().Get("Content-Type"), rec.Body.String())
	}
}

func TestStatusErrorDerivesCodeAndRetryability(t *testing.T) {
	rec := httptest.NewRecorder()
	StatusError(rec, http.StatusConflict, "Already a member")
	body := decodeError(t, rec)
	if rec.Code != 409 || body.Code != "OPERATION_CONFLICT" || body.Message != "Already a member" || body.Retryable {
		t.Fatalf("unexpected 409 error: %d %+v", rec.Code, body)
	}

	rec = httptest.NewRecorder()
	StatusError(rec, http.StatusServiceUnavailable, "Try later")
	if body := decodeError(t, rec); body.Code != "INTERNAL" || !body.Retryable {
		t.Fatalf("5xx errors should be retryable: %+v", body)
	}
}

func TestDecodeIgnoresUnknownFieldsButDecodeStrictRejectsThem(t *testing.T) {
	var target struct {
		Name string `json:"name"`
	}
	body := `{"name":"Ann","extra":true}`

	if err := Decode(httptest.NewRecorder(), httptest.NewRequest("POST", "/", strings.NewReader(body)), &target); err != nil || target.Name != "Ann" {
		t.Fatalf("Decode: err=%v name=%q", err, target.Name)
	}
	if err := DecodeStrict(httptest.NewRecorder(), httptest.NewRequest("POST", "/", strings.NewReader(body)), &target); err == nil {
		t.Fatal("DecodeStrict accepted an unknown field")
	}
}

func TestDecodeEnforcesTheBodyLimit(t *testing.T) {
	var target map[string]string
	oversized := `{"blob":"` + strings.Repeat("x", MaxBodyBytes) + `"}`
	if err := Decode(httptest.NewRecorder(), httptest.NewRequest("POST", "/", strings.NewReader(oversized)), &target); err == nil {
		t.Fatal("Decode read a body larger than MaxBodyBytes")
	}
}

func TestBindJSON(t *testing.T) {
	var target struct {
		Name string `json:"name"`
	}
	rec := httptest.NewRecorder()
	if !BindJSON(rec, httptest.NewRequest("POST", "/", strings.NewReader(`{"name":"Bo"}`)), &target) || target.Name != "Bo" || rec.Body.Len() != 0 {
		t.Fatalf("valid body rejected or a response was written: %s", rec.Body.String())
	}

	for name, body := range map[string]string{"malformed": `{"name":`, "empty": ``} {
		t.Run(name, func(t *testing.T) {
			rec := httptest.NewRecorder()
			if BindJSON(rec, httptest.NewRequest("POST", "/", strings.NewReader(body)), &target) {
				t.Fatal("bad body accepted")
			}
			if got := decodeError(t, rec); rec.Code != 400 || got.Code != "INVALID_INPUT" || got.Message != "Invalid JSON body" {
				t.Fatalf("unexpected error: %d %+v", rec.Code, got)
			}
		})
	}
}

func TestPathUUID(t *testing.T) {
	id := uuid.New()
	req := httptest.NewRequest("GET", "/", nil)
	req.SetPathValue("plan_id", id.String())
	rec := httptest.NewRecorder()
	if got, ok := PathUUID(rec, req, "plan_id", "Invalid Plan UUID format"); !ok || got != id || rec.Body.Len() != 0 {
		t.Fatalf("valid id rejected: ok=%v got=%v body=%s", ok, got, rec.Body.String())
	}

	for _, value := range []string{"", "nope", id.String() + "x"} {
		req := httptest.NewRequest("GET", "/", nil)
		req.SetPathValue("plan_id", value)
		rec := httptest.NewRecorder()
		if _, ok := PathUUID(rec, req, "plan_id", "Invalid Plan UUID format"); ok {
			t.Fatalf("%q accepted as a UUID", value)
		}
		if got := decodeError(t, rec); rec.Code != 400 || got.Code != "INVALID_INPUT" || got.Message != "Invalid Plan UUID format" {
			t.Fatalf("unexpected error for %q: %d %+v", value, rec.Code, got)
		}
	}
}

func TestMiddlewareUsesTheSharedCodeTable(t *testing.T) {
	// Non-JSON errors from the mux are rewritten using CodeForStatus.
	rec := httptest.NewRecorder()
	Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	})).ServeHTTP(rec, httptest.NewRequest("POST", "/health", nil))
	if body := decodeError(t, rec); rec.Code != 405 || body.Code != "METHOD_NOT_ALLOWED" {
		t.Fatalf("unexpected rewrite: %d %+v", rec.Code, body)
	}
}