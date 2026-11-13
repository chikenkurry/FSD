package httpapi

import (
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

type bucket struct {
	started time.Time
	count   int
}

// clock is replaced in tests to move a rate-limit window forward.
var clock = time.Now

// trustedProxies parses TRUSTED_PROXY_CIDRS, e.g. "172.16.0.0/12,10.0.0.0/8".
// Requests arriving from these networks carry the real client in X-Real-IP.
func trustedProxies() []*net.IPNet {
	var nets []*net.IPNet
	for _, cidr := range strings.Split(os.Getenv("TRUSTED_PROXY_CIDRS"), ",") {
		if _, network, err := net.ParseCIDR(strings.TrimSpace(cidr)); err == nil {
			nets = append(nets, network)
		}
	}
	return nets
}

// clientHost keys the rate limit. X-Real-IP is honoured only when the direct
// peer is a configured proxy, so untrusted clients cannot spoof their way out.
func clientHost(r *http.Request, trusted []*net.IPNet) string {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		host = r.RemoteAddr
	}
	peer := net.ParseIP(host)
	if peer == nil {
		return host
	}
	for _, network := range trusted {
		if network.Contains(peer) {
			if real := net.ParseIP(strings.TrimSpace(r.Header.Get("X-Real-IP"))); real != nil {
				return real.String()
			}
			break
		}
	}
	return host
}

// Bounded local admission limits. Proxy headers are ignored unless the peer is
// in TRUSTED_PROXY_CIDRS; a gateway should apply shared limits across replicas.
func Limits(next http.Handler) http.Handler {
	entries := map[string]bucket{}
	trusted := trustedProxies()
	var mutex sync.Mutex
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/v1/") {
			next.ServeHTTP(w, r)
			return
		}
		host := clientHost(r, trusted)
		category, limit := "api", 360
		if r.Method == "POST" && r.URL.Path == "/v1/users" {
			category, limit = "register", 100
		}
		if r.Method == "POST" && (strings.HasSuffix(r.URL.Path, "/preview") || strings.HasSuffix(r.URL.Path, "/recommendations") || strings.HasSuffix(r.URL.Path, "/fact-collection")) {
			category, limit = "compute", 60
		}
		key := host + ":" + category
		now := clock()
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
