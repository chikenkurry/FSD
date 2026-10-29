package httpapi

import (
	"context"
	"encoding/json"
	"github.com/google/uuid"
	"log"
	"net/http"
	"regexp"
	"strings"
	"time"
)

type requestKey struct{}
type errorResponse struct {
	http.ResponseWriter
	muted bool
}

func (w *errorResponse) WriteHeader(code int) {
	if code >= 400 && !strings.Contains(w.Header().Get("Content-Type"), "application/json") {
		w.muted = true
		Error(w.ResponseWriter, code, CodeForStatus(code), http.StatusText(code))
		return
	}
	w.ResponseWriter.WriteHeader(code)
}
func (w *errorResponse) Write(body []byte) (int, error) {
	if w.muted {
		return len(body), nil
	}
	return w.ResponseWriter.Write(body)
}

var safeID = regexp.MustCompile(`^[A-Za-z0-9_-]{8,64}$`)

func RequestID(ctx context.Context) string { id, _ := ctx.Value(requestKey{}).(string); return id }

func Error(w http.ResponseWriter, status int, code, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(map[string]any{"code": code, "message": message,
		"retryable": status >= 500 || status == 429, "requestId": w.Header().Get("x-request-id")})
}

func Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("x-request-id")
		if !safeID.MatchString(id) {
			id = uuid.NewString()
		}
		w.Header().Set("x-request-id", id)
		started := time.Now()
		next.ServeHTTP(&errorResponse{ResponseWriter: w}, r.WithContext(context.WithValue(r.Context(), requestKey{}, id)))
		log.Printf("request_finished request_id=%s method=%s elapsed_ms=%d", id, r.Method, time.Since(started).Milliseconds())
	})
}