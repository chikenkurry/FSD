package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"

	"planning-service/app/internal/config"
	"planning-service/app/internal/database"
	"planning-service/app/internal/handler"
	"planning-service/app/internal/integration"
	"planning-service/app/internal/model"
	"planning-service/app/internal/repository"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

type JsonResponse struct {
	Status  string `json:"status"`
	Message string `json:"message"`
}

var ctx = context.Background()

var joinBaseURL = "http://localhost:8080/join"

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

	// run migrations
	err = db.AutoMigrate(
		&model.User{},
		&integration.Session{},
		&integration.Round{},
		&integration.Selection{},
		&integration.ReopenOperation{},
		&model.Plan{},
		&model.Invitation{},
		&model.Question{},
		&model.QuestionPreset{},
		&model.PlanRound{},
		&model.PlanMember{},
		&model.ProposedActivity{},
		&model.ConfirmedSelection{},
	)
	if err != nil {
		log.Fatalf("AutoMigrate failed: %v", err)
	}
	log.Println("Database migration completed for all tables!")

	// seed preset templates
	if err := database.SeedQuestionPresets(db); err != nil {
		log.Printf("WarningL failed to seed presets: %v", err)
	}

	// Initialize layers
	planRepo := repository.NewPlanRepository(db)
	planHandler := handler.NewPlanHandler(planRepo)

	userRepo := repository.NewUserRepository(db)
	userHandler := handler.NewUserHandler(userRepo)

	questionRepo := repository.NewQuestionRepository(db)
	questionHandler := handler.NewQuestionHandler(questionRepo)

	invitationRepo := repository.NewInvitationRepository(db)
	invitationHandler := handler.NewInvitationHandler(invitationRepo, joinBaseURL)

	planMemberRepo := repository.NewPlanMemberRepository(db)
	planMemberHandler := handler.NewPlanMemberHandler(planMemberRepo)

	proposedActivityRepo := repository.NewProposedActivityRepository(db)
	proposedActivityHandler := handler.NewProposedActivityHandler(proposedActivityRepo)

	planRoundRepo := repository.NewPlanRoundRepository(db)
	planRoundHandler := handler.NewPlanRoundHandler(planRoundRepo)

	selectionRepo := repository.NewConfirmedSelectionRepository(db)
	selectionHandler := handler.NewConfirmedSelectionHandler(selectionRepo)

	mux := http.NewServeMux()
	flow := integration.NewHandler(db, cfg.ParticipationBaseURL, cfg.DecisionBaseURL, cfg.InternalAPIToken)
	if len(cfg.InternalAPIToken) < 16 {
		log.Fatal("INTERNAL_API_TOKEN must have at least 16 characters")
	}

	mux.HandleFunc("GET /health", GetHealth)

	// plans CRUD methods
	mux.HandleFunc("POST /v1/plans", planHandler.CreatePlan) //👌
	mux.HandleFunc("GET /v1/plans/{id}", planHandler.GetPlanById)
	mux.HandleFunc("GET /v1/plans/details/{id}", planHandler.GetByIDWithDetails)
	mux.HandleFunc("GET /v1/plans/organiser/{id}", enableCORS(planHandler.ListPlansByOrganiser))
	mux.HandleFunc("PATCH /v1/plans/{id}", planHandler.UpdatePlan)
	mux.HandleFunc("DELETE /v1/plans/{id}", planHandler.DeletePlan)

	// users CRUD methods
	mux.HandleFunc("POST /v1/users", enableCORS(flow.RegisterUser)) //👌
	mux.HandleFunc("GET /v1/users/{id}", enableCORS(userHandler.GetUserByID))
	mux.HandleFunc("GET /v1/usersbyname/{username}", enableCORS(userHandler.GetUserByUsername))
	mux.HandleFunc("PUT /v1/users/{id}", userHandler.UpdateUser)

	// question CRUD methods
	mux.HandleFunc("POST /v1/question", questionHandler.Create) //👌
	mux.HandleFunc("GET /v1/plans/question/{plan_id}", questionHandler.GetQuestionByPlanId)
	mux.HandleFunc("PATCH /v1/question/{question_id}", questionHandler.UpdateQuestion)
	mux.HandleFunc("DELETE /v1/question/{question_id}", questionHandler.Delete)

	// invitation CRUD methods
	mux.HandleFunc("POST /v1/plans/{plan_id}/invites", invitationHandler.CreateInvitation)
	mux.HandleFunc("POST /v1/invites/{token}/join", invitationHandler.AcceptInvitation)

	// plan member CRUD methods
	mux.HandleFunc("POST /v1/plans/{plan_id}/members", planMemberHandler.AddMember)
	mux.HandleFunc("GET /v1/plan_members/{plan_id}", planMemberHandler.ListMembers)
	mux.HandleFunc("PATCH /v1/members/{id}", planMemberHandler.UpdateMember)
	mux.HandleFunc("DELETE /v1/members/{id}", planMemberHandler.RemoveMember)
	mux.HandleFunc("DELETE /v1/plans/{plan_id}/members/{user_id}", planMemberHandler.RemoveMemberByPlanAndUser)

	// proposed activity CRUD methods
	mux.HandleFunc("POST /v1/proposed_activity/plans/{plan_id}", proposedActivityHandler.CreateActivity)
	mux.HandleFunc("GET /v1/proposed_activity/plans/{plan_id}", proposedActivityHandler.ListActivitiesByPlan)
	mux.HandleFunc("GET /v1/proposed_activity/{id}", proposedActivityHandler.GetActivityByID)
	mux.HandleFunc("PATCH /v1/proposed_activity/{id}", proposedActivityHandler.UpdateActivity)
	mux.HandleFunc("DELETE /v1/proposed_activity/{id}", proposedActivityHandler.DeleteActivity)

	// round CRUD methods
	mux.HandleFunc("GET /v1/rounds/{id}", planRoundHandler.GetRoundByID)
	mux.HandleFunc("PATCH /v1/rounds/{id}", planRoundHandler.UpdateRound)
	mux.HandleFunc("DELETE /v1/rounds/{id}", planRoundHandler.DeleteRound)
	mux.HandleFunc("POST /v1/rounds/open/{id}", flow.Publish)

	mux.HandleFunc("POST /internal/sessions/authorise", flow.Internal(flow.AuthoriseSession))
	mux.HandleFunc("GET /internal/rounds/{id}/option-snapshot", flow.Internal(flow.Snapshot))

	flow.RegisterRoundRoutes(mux, planRoundHandler.CreateRound, planRoundHandler.ListRoundsByPlan)

	// selection CRUD methods
	mux.HandleFunc("POST /v1/confirmed-selection/plans/{plan_id}", selectionHandler.CreateConfirmedSelection)
	mux.HandleFunc("GET /v1/confirmed-selection/plans/{plan_id}", selectionHandler.GetConfirmedSelectionByPlan)

	// start Server
	log.Println("Planning Service running on :8080...")
	if err := http.ListenAndServe(":8080", flow.Guard(mux)); err != nil {
		log.Fatalf("Server stopped: %v", err)
	}
}

func GetHealth(w http.ResponseWriter, r *http.Request) {
	result := JsonResponse{Status: "okay", Message: "service be alive"}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}

func enableCORS(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "http://localhost:5173")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")

		// Handle preflight OPTIONS requests
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}

		next(w, r)
	}
}
