package httpapi

import (
	"net"
	"net/http"
	"strings"
	"sync"
	"time"
)

type bucket struct {
	started time.Time
	count   int
}

// Bounded local admission limits. Untrusted proxy headers cannot bypass this
// limit. A gateway should apply shared limits when deploying several replicas.
func Limits(next http.Handler) http.Handler {
	entries := map[string]bucket{}
	var mutex sync.Mutex
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/v1/") {
			next.ServeHTTP(w, r)
			return
		}
		host, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil {
			host = r.RemoteAddr
		}
		category, limit := "api", 360
		if r.Method == "POST" && r.URL.Path == "/v1/users" {
			category, limit = "register", 100
		}
		if r.Method == "POST" && (strings.HasSuffix(r.URL.Path, "/preview") || strings.HasSuffix(r.URL.Path, "/recommendations") || strings.HasSuffix(r.URL.Path, "/fact-collection")) {
			category, limit = "compute", 60
		}
		key := host + ":" + category
		now := time.Now()
		mutex.Lock()
		if len(entries) >= 4096 {
			for key, value := range entries {
				if now.Sub(value.started) > time.Minute {
					delete(entries, key)
				}
			}
		}
		current, exists := entries[key]
		allowed := exists || len(entries) < 4096
		if now.Sub(current.started) > time.Minute {
			current = bucket{started: now}
		}
		if current.count >= limit {
			allowed = false
		}
		if allowed {
			current.count++
			entries[key] = current
		}
		mutex.Unlock()
		if !allowed {
			w.Header().Set("Retry-After", "60")
			Error(w, 429, "RATE_LIMITED", "Please retry later")
			return
		}
		next.ServeHTTP(w, r)
	})
}
