package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"github.com/google/uuid"
	"gorm.io/datatypes"
)

type CreateQuestionRequest struct {
	PlanID      uuid.UUID          `json:"plan_id"`
	Title       string             `json:"title"`
	Type        model.QuestionType `json:"question_type"`
	Description *string            `json:"description,omitempty"`
	IsRequired  bool               `json:"is_required"`
	SortOrder   int                `json:"sort_order,omitempty"`
	Options     datatypes.JSON     `json:"options,omitempty"`
}

type UpdateQuestionRequest struct {
	ID          uuid.UUID           `json:"id"`
	Title       *string             `json:"title"`
	Type        *model.QuestionType `json:"question_type"`
	Description *string             `json:"description,omitempty"`
	IsRequired  *bool               `json:"is_required"`
	SortOrder   *int                `json:"sort_order,omitempty"`
	Options     datatypes.JSON      `json:"options,omitempty"` // e.g. {"options": ["Italian", "Japanese", "Mexican"], "allow_other": true}
}

type QuestionHandler struct {
	repo *repository.QuestionRepository
}

func NewQuestionHandler(repo *repository.QuestionRepository) *QuestionHandler {
	return &QuestionHandler{repo: repo}
}

// POST /v1/question
func (h *QuestionHandler) Create(w http.ResponseWriter, r *http.Request) {
	var req CreateQuestionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON payload")
		return
	}

	if req.Title == "" || req.PlanID == uuid.Nil {
		WriteError(w, http.StatusBadRequest, "title and plan id are required")
		return
	}

	question := &model.Question{
		PlanID: req.PlanID,
		Title: req.Title,
		Type: req.Type,
		Description: req.Description,
		IsRequired: req.IsRequired,
		SortOrder: req.SortOrder,
	}
	if err := h.repo.Create(r.Context(), question); err != nil {
		WriteError(w, http.StatusInternalServerError, "Fail to create question")
		return
	}
	WriteJSONResponse(w, http.StatusCreated, question)
}

// GET /v1/plans/question/{plan_id}
func (h *QuestionHandler)GetQuestionByPlanId(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("plan_id")
	planID, err := uuid.Parse(id)
	if err != nil{
		WriteError(w, http.StatusBadRequest, "Invalid Plan UUID format")
		return
	}
	questions, err := h.repo.ListByPlanID(r.Context(), planID)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, "Failed to list questions")
		return
	}
	WriteJSONResponse(w, http.StatusOK, questions)
}

// PATCH /v1/question/{question_id}
func (h *QuestionHandler) UpdateQuestion(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("question_id")
	questionID, err := uuid.Parse(id)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Question UUID format")
	}

	var req UpdateQuestionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid JSON body")
		return
	}

	// Build dynamic updates map
	updates := make(map[string]interface{})
	if req.Title != nil {
		updates["title"] = req.Title
	}
	if req.Description != nil {
		updates["description"] = req.Description
	}
	if req.Type != nil {
		updates["type"] = req.Type
	}
	if req.IsRequired != nil {
		updates["is_required"] = req.IsRequired
	}
	if req.SortOrder != nil {
		updates["sort_order"] = req.SortOrder
	}
	if req.Options != nil {
		updates["options"] = req.Options
	}

	if len(updates) == 0 {
		WriteError(w, http.StatusBadRequest, "No fields provided to update")
		return
	}

	updatedQuestion, err := h.repo.Update(r.Context(), questionID, updates)
	if err != nil {
		if errors.Is(err, repository.ErrQuestionNotFound) {
			WriteError(w, http.StatusNotFound, "question not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to update question")
		return
	}

	WriteJSONResponse(w, http.StatusOK, updatedQuestion)
}

// Delete /v1/question/{question_id}
func (h *QuestionHandler) Delete(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("question_id")
	questionID, err := uuid.Parse(id)
	if err != nil {
		WriteError(w, http.StatusBadRequest, "Invalid Question UUID format")
	}

	if err := h.repo.Delete(r.Context(), questionID); err != nil {
		if errors.Is(err, repository.ErrQuestionNotFound) {
			WriteError(w, http.StatusNotFound, "Question not found")
			return
		}
		WriteError(w, http.StatusInternalServerError, "Failed to delete question")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}