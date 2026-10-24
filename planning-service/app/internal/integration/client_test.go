package integration

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestSnapshotGetHasNoJSONNullBody(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		if len(body) != 0 {
			t.Errorf("GET body must be empty; got %q", body)
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status":"ok"}`))
	}))
	defer server.Close()
	handler := NewHandler(nil, "", "", "fixture-internal-token")
	if _, err := handler.call(context.Background(), server.URL, "GET", "/internal/test", nil); err != nil {
		t.Fatal(err)
	}
}
