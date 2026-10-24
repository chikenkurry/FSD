package handler

import (
	"encoding/json"
	"net/http"
	"planning-service/app/internal/httpapi"
)

// helper utilties

func WriteJSONResponse(w http.ResponseWriter, status int, payload interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(payload)
}

func WriteError(w http.ResponseWriter, status int, message string) {
	codes := map[int]string{400: "INVALID_INPUT", 401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "OPERATION_CONFLICT", 410: "EXPIRED", 429: "RATE_LIMITED"}
	code := codes[status]
	if code == "" {
		code = "INTERNAL"
	}
	httpapi.Error(w, status, code, message)
}
