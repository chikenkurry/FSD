package integration

import "net/http"

// One dispatcher preserves the existing /rounds/plans/{plan_id} routes without
// ambiguous ServeMux patterns such as /rounds/{id}/publish.
func (h *Handler) RegisterRoundRoutes(mux *http.ServeMux, create, list http.HandlerFunc) {
	posts := map[string]http.HandlerFunc{"publish": h.Publish, "close": h.Close, "recommendations": h.Recommend, "confirm": h.Confirm, "reopen": h.Reopen, "preview": h.Preview, "fact-collection": h.CollectFacts, "accept-facts": h.AcceptFacts, "research": h.Research}
	gets := map[string]http.HandlerFunc{"form": h.Snapshot, "recommendation": h.Result, "clarifications": h.Clarifications, "selection": h.GetSelection, "preview": h.GetPreview, "readiness": h.Readiness, "fact-collection": h.GetFactCollection, "research": h.GetResearch, "place": h.Place, "place-photo": h.PlacePhoto}
	dispatch := func(method string, actions map[string]http.HandlerFunc, plans http.HandlerFunc) {
		mux.HandleFunc(method+" /v1/rounds/{id}/{action}", func(w http.ResponseWriter, r *http.Request) {
			if r.PathValue("id") == "plans" {
				r.SetPathValue("plan_id", r.PathValue("action"))
				plans(w, r)
				return
			}
			action, ok := actions[r.PathValue("action")]
			if !ok {
				fail(w, 404, "NOT_FOUND")
				return
			}
			action(w, r)
		})
	}
	dispatch("POST", posts, create)
	gets["draft"] = h.GetCreatorDraft
	dispatch("GET", gets, list)
	dispatch("PUT", map[string]http.HandlerFunc{"draft": h.DefinitionCommand(h.SaveCreatorDraft)}, func(w http.ResponseWriter, r *http.Request) { fail(w, 404, "NOT_FOUND") })
}
