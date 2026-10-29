package handler

import (
	"errors"
	"net/http"

	"planning-service/app/internal/httpapi"
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
	if !httpapi.BindJSON(w, r, &req) {
		return
	}

	if req.Title == "" || req.PlanID == uuid.Nil {
		httpapi.StatusError(w, http.StatusBadRequest, "title and plan id are required")
		return
	}

	question := &model.Question{
		PlanID:      req.PlanID,
		Title:       req.Title,
		Type:        req.Type,
		Description: req.Description,
		IsRequired:  req.IsRequired,
		SortOrder:   req.SortOrder,
		Options:     req.Options,
	}
	if err := h.repo.Create(r.Context(), question); err != nil {
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to create question")
		return
	}
	httpapi.JSON(w, http.StatusCreated, question)
}

// GET /v1/plans/question/{plan_id}
func (h *QuestionHandler) GetQuestionByPlanId(w http.ResponseWriter, r *http.Request) {
	planID, ok := httpapi.PathUUID(w, r, "plan_id", "Invalid Plan UUID format")
	if !ok {
		return
	}
	questions, err := h.repo.ListByPlanID(r.Context(), planID)
	if err != nil {
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to list questions")
		return
	}
	httpapi.JSON(w, http.StatusOK, questions)
}

// PATCH /v1/question/{question_id}
func (h *QuestionHandler) UpdateQuestion(w http.ResponseWriter, r *http.Request) {
	questionID, ok := httpapi.PathUUID(w, r, "question_id", "Invalid Question UUID format")
	if !ok {
		return
	}

	var req UpdateQuestionRequest
	if !httpapi.BindJSON(w, r, &req) {
		return
	}

	// Build dynamic updates map
	updates := make(map[string]interface{})
	if req.Title != nil {
		updates["title"] = *req.Title
	}
	if req.Description != nil {
		updates["description"] = req.Description
	}
	if req.Type != nil {
		updates["type"] = *req.Type
	}
	if req.IsRequired != nil {
		updates["is_required"] = *req.IsRequired
	}
	if req.SortOrder != nil {
		updates["sort_order"] = *req.SortOrder
	}
	if req.Options != nil {
		updates["options"] = req.Options
	}

	if len(updates) == 0 {
		httpapi.StatusError(w, http.StatusBadRequest, "No fields provided to update")
		return
	}

	updatedQuestion, err := h.repo.Update(r.Context(), questionID, updates)
	if err != nil {
		if errors.Is(err, repository.ErrQuestionNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "Question not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to update question")
		return
	}

	httpapi.JSON(w, http.StatusOK, updatedQuestion)
}

// DELETE /v1/question/{question_id}
func (h *QuestionHandler) Delete(w http.ResponseWriter, r *http.Request) {
	questionID, ok := httpapi.PathUUID(w, r, "question_id", "Invalid Question UUID format")
	if !ok {
		return
	}

	if err := h.repo.Delete(r.Context(), questionID); err != nil {
		if errors.Is(err, repository.ErrQuestionNotFound) {
			httpapi.StatusError(w, http.StatusNotFound, "Question not found")
			return
		}
		httpapi.StatusError(w, http.StatusInternalServerError, "Failed to delete question")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}
