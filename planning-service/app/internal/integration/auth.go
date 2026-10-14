package integration

import (
	"context"
	"net/http"
	"strings"

	"github.com/google/uuid"
)

func (h *Handler) Guard(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/v1/") || (r.Method == "POST" && r.URL.Path == "/v1/users") {
			next.ServeHTTP(w, r)
			return
		}
		bearer := r.Header.Get("Authorization")
		if !strings.HasPrefix(bearer, "Bearer ") {
			fail(w, 401, "UNAUTHENTICATED")
			return
		}
		user, err := h.sessionUser(r.Context(), strings.TrimPrefix(bearer, "Bearer "))
		if err != nil {
			fail(w, 401, "UNAUTHENTICATED")
			return
		}
		r = r.WithContext(context.WithValue(r.Context(), userKey{}, user))
		parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
		write := r.Method != "GET"
		var bodyPlanID uuid.UUID
		if write {
			var allowed bool
			bodyPlanID, allowed = validateMutationBody(w, r, parts, user)
			if !allowed {
				return
			}
		}
		planID, ok := h.planForPath(parts, user)
		if !ok && len(parts) == 2 && parts[1] == "question" && r.Method == "POST" && bodyPlanID != uuid.Nil {
			planID, ok = bodyPlanID, true
		}
		if !ok {
			fail(w, 403, "FORBIDDEN")
			return
		}
		memberWrite := len(parts) == 4 && parts[1] == "rounds" && parts[3] == "preview"
		if planID != uuid.Nil && !h.member(user, planID, write && !memberWrite) {
			fail(w, 403, "FORBIDDEN")
			return
		}
		if planID != uuid.Nil && write && !h.allowPlanMutation(w, r, parts, planID) {
			return
		}
		r = r.WithContext(context.WithValue(r.Context(), planKey{}, planID))
		next.ServeHTTP(w, r)
	})
}
