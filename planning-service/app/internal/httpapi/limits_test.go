package httpapi

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func allowAll() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusNoContent) })
}

func send(handler http.Handler, method, path, remoteAddr string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, nil)
	request.RemoteAddr = remoteAddr
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

// exhaust sends limit allowed requests and fails if any is rejected early.
func exhaust(t *testing.T, handler http.Handler, method, path, remoteAddr string, limit int) {
	t.Helper()
	for i := 1; i <= limit; i++ {
		if code := send(handler, method, path, remoteAddr).Code; code != http.StatusNoContent {
			t.Fatalf("request %d of %d to %s %s returned %d", i, limit, method, path, code)
		}
	}
}

func assertLimited(t *testing.T, response *httptest.ResponseRecorder) {
	t.Helper()
	var body map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("rate-limit response is not JSON: %v", err)
	}
	if response.Code != http.StatusTooManyRequests || response.Header().Get("Retry-After") != "60" || body["code"] != "RATE_LIMITED" || body["retryable"] != true {
		t.Fatalf("expected the rate-limit contract, got status=%d retry-after=%q body=%v", response.Code, response.Header().Get("Retry-After"), body)
	}
}

// freezeClock pins the limiter's clock and returns a function that advances it.
func freezeClock(t *testing.T) func(time.Duration) {
	t.Helper()
	now := time.Date(2026, 10, 29, 9, 0, 0, 0, time.UTC)
	clock = func() time.Time { return now }
	t.Cleanup(func() { clock = time.Now })
	return func(step time.Duration) { now = now.Add(step) }
}

func TestLimitsEachCategoryPerMinute(t *testing.T) {
	cases := []struct {
		name, method, path string
		limit              int
	}{
		{"general API reads", "GET", "/v1/plans/123", 360},
		{"general API writes", "PATCH", "/v1/plans/123", 360},
		{"guest registration", "POST", "/v1/users", 100},
		{"answer previews", "POST", "/v1/rounds/123/preview", 60},
		{"recommendations", "POST", "/v1/rounds/123/recommendations", 60},
		{"fact collection", "POST", "/v1/rounds/123/fact-collection", 60},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			freezeClock(t)
			handler := Limits(allowAll())
			exhaust(t, handler, test.method, test.path, "10.0.0.1:5000", test.limit)
			assertLimited(t, send(handler, test.method, test.path, "10.0.0.1:5000"))
		})
	}
}

func TestComputeReadsUseTheGeneralBudget(t *testing.T) {
	freezeClock(t)
	handler := Limits(allowAll())
	// Polling a recommendation is a GET, so it must not consume the 60/min compute budget.
	exhaust(t, handler, "GET", "/v1/rounds/123/recommendation", "10.0.0.1:5000", 360)
	assertLimited(t, send(handler, "GET", "/v1/rounds/123/recommendation", "10.0.0.1:5000"))
}

func TestCategoriesAreCountedSeparately(t *testing.T) {
	freezeClock(t)
	handler := Limits(allowAll())
	exhaust(t, handler, "POST", "/v1/rounds/123/recommendations", "10.0.0.1:5000", 60)
	assertLimited(t, send(handler, "POST", "/v1/rounds/123/preview", "10.0.0.1:5000"))
	if code := send(handler, "GET", "/v1/plans/123", "10.0.0.1:5000").Code; code != http.StatusNoContent {
		t.Fatalf("exhausting compute blocked ordinary API reads: %d", code)
	}
	if code := send(handler, "POST", "/v1/users", "10.0.0.1:5000").Code; code != http.StatusNoContent {
		t.Fatalf("exhausting compute blocked registration: %d", code)
	}
}

func TestClientsAreKeyedByHostNotPort(t *testing.T) {
	freezeClock(t)
	handler := Limits(allowAll())
	exhaust(t, handler, "POST", "/v1/users", "10.0.0.1:5000", 100)
	assertLimited(t, send(handler, "POST", "/v1/users", "10.0.0.1:6000"))
	if code := send(handler, "POST", "/v1/users", "10.0.0.2:5000").Code; code != http.StatusNoContent {
		t.Fatalf("another client was limited by the first client's usage: %d", code)
	}
}

func TestForwardedHeadersCannotBypassTheLimit(t *testing.T) {
	freezeClock(t)
	handler := Limits(allowAll())
	exhaust(t, handler, "POST", "/v1/users", "10.0.0.1:5000", 100)
	request := httptest.NewRequest("POST", "/v1/users", nil)
	request.RemoteAddr = "10.0.0.1:5000"
	request.Header.Set("X-Forwarded-For", "203.0.113.9")
	request.Header.Set("X-Real-IP", "203.0.113.9")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	assertLimited(t, response)
}

func TestNonAPIPathsAreNotLimited(t *testing.T) {
	freezeClock(t)
	handler := Limits(allowAll())
	exhaust(t, handler, "GET", "/v1/plans/123", "10.0.0.1:5000", 360)
	for _, path := range []string{"/health", "/health/ready", "/internal/sessions/authorise"} {
		if code := send(handler, "GET", path, "10.0.0.1:5000").Code; code != http.StatusNoContent {
			t.Fatalf("%s was rate limited: %d", path, code)
		}
	}
}

func TestWindowResetsAfterAMinute(t *testing.T) {
	advance := freezeClock(t)
	handler := Limits(allowAll())
	exhaust(t, handler, "POST", "/v1/users", "10.0.0.1:5000", 100)
	advance(59 * time.Second)
	assertLimited(t, send(handler, "POST", "/v1/users", "10.0.0.1:5000"))
	advance(2 * time.Second)
	exhaust(t, handler, "POST", "/v1/users", "10.0.0.1:5000", 100)
	assertLimited(t, send(handler, "POST", "/v1/users", "10.0.0.1:5000"))
}

func TestFullTableRejectsNewClientsUntilEntriesExpire(t *testing.T) {
	advance := freezeClock(t)
	handler := Limits(allowAll())
	host := func(i int) string { return fmt.Sprintf("10.%d.%d.1:5000", i/256, i%256) }
	for i := 0; i < 4096; i++ {
		if code := send(handler, "GET", "/v1/plans/123", host(i)).Code; code != http.StatusNoContent {
			t.Fatalf("client %d was rejected before the table filled: %d", i, code)
		}
	}
	assertLimited(t, send(handler, "GET", "/v1/plans/123", "192.0.2.1:5000"))
	if code := send(handler, "GET", "/v1/plans/123", host(7)).Code; code != http.StatusNoContent {
		t.Fatalf("a known client was rejected because the table was full: %d", code)
	}
	advance(61 * time.Second)
	if code := send(handler, "GET", "/v1/plans/123", "192.0.2.1:5000").Code; code != http.StatusNoContent {
		t.Fatalf("expired entries were not cleared for a new client: %d", code)
	}
}
