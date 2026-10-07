package database

import (
	"log"

	"planning-service/app/internal/model"

	"gorm.io/datatypes"
	"gorm.io/gorm"
)

// SeedQuestionPresets inserts default question templates into the database
func SeedQuestionPresets(db *gorm.DB) error{
	presets := []model.QuestionPreset {
		// TRAVEL PRESETS
		{
			Category:    model.CategoryTravel,
			Title:       "Where should we go?",
			Type:        model.QuestionTypeLocation,
			Description: "Suggest or vote on target destinations for the trip.",
			IsRequired:  true,
		},
		{
			Category:    model.CategoryTravel,
			Title:       "How many days should the trip be?",
			Type:        model.QuestionTypeDuration,
			Description: "Estimate duration for travel planning.",
			IsRequired:  true,
		},
		{
			Category: model.CategoryTravel,
			Title: "What is your budget?",
			Type: model.QuestionTypeBudget,
			Description: "Helps narrow down lodging and transport options.",
			IsRequired: false,
			Options:     datatypes.JSON([]byte(`{"currency": "SGD", "suggested_ranges": ["<$500", "$500-$1500", "$1500+"]}`)),
		},

		// DINNING PRESETS
		{
			Category:    model.CategoryDining,
			Title:       "What cuisine would you prefer?",
			Type:        model.QuestionTypeCustomSingleChoice,
			Description: "Select your top choice.",
			IsRequired:  true,
			Options:     datatypes.JSON([]byte(`{"choices": ["Italian", "Japanese", "Mexican", "Korean BBQ", "Open to anything"]}`)),
		},
		{
			Category:    model.CategoryDining,
			Title:       "Any dietary restrictions?",
			Type:        model.QuestionTypeCustomText,
			Description: "List allergies, vegan, halal, vegetarian requirements.",
			IsRequired:  false,
			SortOrder:   2,
		},
		{
			Category:    model.CategoryDining,
			Title:       "What time works best for dinner?",
			Type:        model.QuestionTypeMeetingTime,
			IsRequired:  true,
			SortOrder:   3,
		},
	}
	for _, preset := range presets {
		err := db.Where(model.QuestionPreset{
			Category: preset.Category,
			Title:    preset.Title,
		}).FirstOrCreate(&preset).Error

		if err != nil {
			return err
		}
	}

	log.Println("Successfully seeded question presets.")
	return nil
}