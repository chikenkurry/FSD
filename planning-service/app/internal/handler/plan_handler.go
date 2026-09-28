package handler

import (
	"encoding/json"
	"net/http"
	"planning-service/app/internal/repository"
)

// for incoming create request
type CreatePlanRequest struct {
	Title       string  `json:"title"`
	Description *string `json:"description"`
	OrganiserID string  `json:"organiser_id"`
}

type PlanHandler struct {
	repo *repository.PlanRepository
}

type JsonResponse struct {
	Status string `json:"status"`
	Message string `json:"message"`
}

func NewPlanHandler(repo *repository.PlanRepository) *PlanHandler {
	return &PlanHandler{repo: repo}
}

func (h *PlanHandler) GetHealth(w http.ResponseWriter, r *http.Request) {
	result := JsonResponse{Status: "okay", Message: "service be alive"}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

// GET /v1/plans/{id}
func (h *PlanHandler) GetPlanById(w http.ResponseWriter, r *http.Request) {
	// w.Header().Set("Content-Type", "application/json")
	id := r.PathValue("id")
	if id == "" {
		http.Error(w, "Plan id is required", http.StatusBadRequest)
		return
	}

	plan, err := h.repo.GetPlanById(r.Context(), id)

	if err != nil {
		if err.Error() == "plan not found"{
			http.Error(w, "Plan not found", http.StatusNotFound)
			return
		}
		http.Error(w, "Fail to retreieve plan", http.StatusInternalServerError)
		return
	}

	writeJSONResponse(w, http.StatusOK, plan)
}

// GET /v1/plans/{organiser_id} - List plans for an organiser
func (h *PlanHandler) ListPlansByOrganiser(w http.ResponseWriter, r *http.Request) {
	organiserID := r.URL.Query().Get("organiser_id")
	if organiserID == "" {
		http.Error(w, "Organiser id is required", http.StatusBadRequest)
		return
	}

	plans, err := h.repo.ListByOrganiser(r.Context(), organiserID, 20, 0)
	if err != nil {
		http.Error(w, "Failed to list plans", http.StatusInternalServerError)
		return
	}
	writeJSONResponse(w, http.StatusOK, plans)
}


// helper funcs

func writeJSONResponse(w http.ResponseWriter, status int, payload interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(payload)
}
