package main

import (
	"os"
	"regexp"
	"sort"
	"strings"
	"testing"
)

var pathParam = regexp.MustCompile(`\{[^}]+\}`)

// route normalises parameter names so /v1/plans/{id} and /v1/plans/{plan_id} compare equal.
func route(method, path string) string {
	return strings.ToUpper(method) + " " + pathParam.ReplaceAllString(path, "{}")
}

func read(t *testing.T, name string) string {
	t.Helper()
	contents, err := os.ReadFile(name)
	if err != nil {
		t.Fatal(err)
	}
	return string(contents)
}

// registeredRoutes reads the routes from main.go and the round dispatcher.
func registeredRoutes(t *testing.T) map[string]bool {
	routes := map[string]bool{}
	for _, match := range regexp.MustCompile(`mux\.HandleFunc\("(\w+) ([^"]+)"`).FindAllStringSubmatch(read(t, "main.go"), -1) {
		routes[route(match[1], match[2])] = true
	}
	dispatcher := read(t, "../internal/integration/routes.go")
	actions := regexp.MustCompile(`"([a-z-]+)":\s*h\.`)
	for _, line := range strings.Split(dispatcher, "\n") {
		method := ""
		switch {
		case strings.Contains(line, "posts :="):
			method = "POST"
		case strings.Contains(line, "gets :=") || strings.Contains(line, "gets["):
			method = "GET"
		case strings.Contains(line, `dispatch("PUT"`):
			method = "PUT"
		}
		if method == "" {
			continue
		}
		for _, match := range actions.FindAllStringSubmatch(line, -1) {
			routes[route(method, "/v1/rounds/{id}/"+match[1])] = true
		}
		if match := regexp.MustCompile(`gets\["([a-z-]+)"\]`).FindStringSubmatch(line); match != nil {
			routes[route(method, "/v1/rounds/{id}/"+match[1])] = true
		}
	}
	// The dispatcher's plan fallback serves round creation and listing.
	routes[route("POST", "/v1/rounds/plans/{plan_id}")] = true
	routes[route("GET", "/v1/rounds/plans/{plan_id}")] = true
	if len(routes) < 50 {
		t.Fatalf("found only %d routes; the route parser no longer matches the source", len(routes))
	}
	return routes
}

func documentedRoutes(t *testing.T) map[string]bool {
	routes := map[string]bool{}
	path := ""
	for _, line := range strings.Split(string(openAPISpec), "\n") {
		if match := regexp.MustCompile(`^  (/\S*):$`).FindStringSubmatch(line); match != nil {
			path = match[1]
		} else if match := regexp.MustCompile(`^    (get|post|put|patch|delete):$`).FindStringSubmatch(line); match != nil && path != "" {
			routes[route(match[1], path)] = true
		} else if strings.HasPrefix(line, "components:") {
			break
		}
	}
	return routes
}

func missing(from, in map[string]bool) []string {
	var result []string
	for route := range from {
		if !in[route] {
			result = append(result, route)
		}
	}
	sort.Strings(result)
	return result
}

func TestOpenAPIDocumentsEveryRoute(t *testing.T) {
	registered, documented := registeredRoutes(t), documentedRoutes(t)
	if undocumented := missing(registered, documented); len(undocumented) > 0 {
		t.Errorf("routes missing from openapi.yaml:\n  %s", strings.Join(undocumented, "\n  "))
	}
	if stale := missing(documented, registered); len(stale) > 0 {
		t.Errorf("openapi.yaml documents routes the service does not serve:\n  %s", strings.Join(stale, "\n  "))
	}
}
