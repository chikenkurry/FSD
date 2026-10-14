package httpapi

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestUnknownRouteUsesErrorContractAndRequestID(t *testing.T) {
	request := httptest.NewRequest("GET", "/unknown", nil)
	request.Header.Set("x-request-id", "fixture_request_123")
	response := httptest.NewRecorder()
	Middleware(http.HandlerFunc(http.NotFound)).ServeHTTP(response, request)
	var body map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if response.Code != 404 || body["code"] != "NOT_FOUND" || body["requestId"] != "fixture_request_123" || body["retryable"] != false {
		t.Fatalf("unexpected error contract: %v", body)
	}
}
