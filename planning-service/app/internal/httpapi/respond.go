package httpapi

/*
Shared request and response helpers. Every package that serves HTTP should
use these rather than encoding JSON or parsing path IDs itself, so the error
contract (see Error) and body limits stay identical across the service.
*/

import (
	"encoding/json"
	"net/http"

	"github.com/google/uuid"
)

// MaxBodyBytes caps how much of a request body Decode and DecodeStrict will read.
const MaxBodyBytes = 2_000_000

// statusCodes maps HTTP statuses to the error codes clients see. Statuses not
// listed here are reported as INTERNAL.
var statusCodes = map[int]string{
	http.StatusBadRequest:          "INVALID_INPUT",
	http.StatusUnauthorized:        "UNAUTHENTICATED",
	http.StatusForbidden:           "FORBIDDEN",
	http.StatusNotFound:            "NOT_FOUND",
	http.StatusMethodNotAllowed:    "METHOD_NOT_ALLOWED",
	http.StatusConflict:            "OPERATION_CONFLICT",
	http.StatusGone:                "EXPIRED",
	http.StatusTooManyRequests:     "RATE_LIMITED",
	http.StatusInternalServerError: "INTERNAL",
}

// CodeForStatus returns the default error code for an HTTP status.
func CodeForStatus(status int) string {
	if code, ok := statusCodes[status]; ok {
		return code
	}
	return "INTERNAL"
}

// JSON writes body as a JSON response with the given status.
func JSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(body)
}

// StatusError writes an error whose code is derived from the status. Use Error
// when the client needs a more specific code than the status implies.
func StatusError(w http.ResponseWriter, status int, message string) {
	Error(w, status, CodeForStatus(status), message)
}

// Decode reads a JSON request body of at most MaxBodyBytes into value. Unknown
// fields are ignored.
func Decode(w http.ResponseWriter, r *http.Request, value any) error {
	return json.NewDecoder(http.MaxBytesReader(w, r.Body, MaxBodyBytes)).Decode(value)
}

// DecodeStrict is Decode, but rejects fields that value does not declare.
func DecodeStrict(w http.ResponseWriter, r *http.Request, value any) error {
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, MaxBodyBytes))
	decoder.DisallowUnknownFields()
	return decoder.Decode(value)
}

// BindJSON decodes the request body into value. If the body is missing,
// malformed or too large it writes a 400 and returns false; callers should
// return immediately in that case.
func BindJSON(w http.ResponseWriter, r *http.Request, value any) bool {
	if err := Decode(w, r, value); err != nil {
		StatusError(w, http.StatusBadRequest, "Invalid JSON body")
		return false
	}
	return true
}

// PathUUID parses the named path value as a UUID. If it is not one, it writes a
// 400 with message and returns false; callers should return immediately.
func PathUUID(w http.ResponseWriter, r *http.Request, name, message string) (uuid.UUID, bool) {
	id, err := uuid.Parse(r.PathValue(name))
	if err != nil {
		StatusError(w, http.StatusBadRequest, message)
		return uuid.Nil, false
	}
	return id, true
}
