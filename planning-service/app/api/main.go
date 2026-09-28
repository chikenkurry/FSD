package main

import (
	"context"
	"log"
	"net/http"

	"planning-service/app/internal/handler"
	"planning-service/app/internal/repository"
	"planning-service/app/internal/config"
	"planning-service/app/internal/model"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)


type JsonResponse struct {
	Status string `json:"status"`
	Message string `json:"message"`
}


var ctx = context.Background()


func main() {
	cfg, err := config.Load()

	if err != nil {
		log.Fatalf("Configuration error: %v", err)
	}

	// Connect to GORM using the loaded DSN
	db, err := gorm.Open(postgres.Open(cfg.DatabaseDSN), &gorm.Config{})
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}

	log.Println("Successfully connected to PostgreSQL database!")
	_ = db

	err = db.AutoMigrate(
		&model.User{},
		&model.Plan{},
		&model.PlanRound{},
		&model.PlanMember{},
		&model.Invitation{},
		&model.ProposedActivity{},
		&model.ConfirmedSelection{},
	)
	if err != nil {
		log.Fatalf("AutoMigrate failed: %v", err)
	}
	log.Println("Database migration completed for all tables!")

	// Initialize layers
	planRepo := repository.NewPlanRepository(db)
	planHandler := handler.NewPlanHandler(planRepo)
	userRepo := repository.NewUserRepository(db)
	userHandler := handler.NewUserHandler(userRepo)

	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", planHandler.GetHealth)

	// plans CRUD methods
	mux.HandleFunc("GET /v1/plans/{id}", planHandler.GetPlanById)

	// users CRUD methods
	mux.HandleFunc("POST /v1/users", userHandler.CreateUser)
	mux.HandleFunc("GET /v1/users/{id}", userHandler.GetUserByID)
	mux.HandleFunc("PUT /v1/users/{id}", userHandler.UpdateUser)


	// start Server
	log.Println("Planning Service running on :8080...")
	if err := http.ListenAndServe(":8080", mux); err != nil {
		log.Fatalf("Server stopped: %v", err)
	}
}