package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"os/signal"
	"planning-service/app/internal/httpapi"
	"syscall"
	"time"

	"planning-service/app/internal/config"
	"planning-service/app/internal/database"
	"planning-service/app/internal/handler"
	"planning-service/app/internal/integration"
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
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		client := &http.Client{Timeout: 2 * time.Second}
		response, err := client.Get("http://127.0.0.1:8080/health/ready")
		if err != nil {
			os.Exit(1)
		}
		defer response.Body.Close()
		if response.StatusCode != 200 {
			os.Exit(1)
		}
		return
	}
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

	if err := database.Migrate(db); err != nil {
		log.Fatalf("Migration failed: %v", err)
	}

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

	mux := http.NewServeMux()
	flow := integration.NewHandler(db, cfg.ParticipationBaseURL, cfg.DecisionBaseURL, cfg.InternalAPIToken)
	if len(cfg.InternalAPIToken) < 16 {
		log.Fatal("INTERNAL_API_TOKEN must have at least 16 characters")
	}

	mux.HandleFunc("GET /health", GetHealth)
	mux.HandleFunc("GET /health/ready", flow.Ready)

	// plans CRUD methods
	mux.HandleFunc("POST /v1/plans", planHandler.CreatePlan) //👌
	mux.HandleFunc("GET /v1/plans/{id}", planHandler.GetPlanById)
	mux.HandleFunc("GET /v1/plans/details/{id}", planHandler.GetByIDWithDetails)
	mux.HandleFunc("GET /v1/plans/organiser/{id}", planHandler.ListPlansByOrganiser)
	mux.HandleFunc("GET /v1/plans/member/{id}", planHandler.ListPlansByMember)
	mux.HandleFunc("PATCH /v1/plans/{id}", flow.DefinitionCommand(planHandler.UpdatePlan))
	mux.HandleFunc("DELETE /v1/plans/{id}", flow.DefinitionCommand(planHandler.DeletePlan))

	// users CRUD methods
	mux.HandleFunc("POST /v1/users", flow.RegisterUser) //👌
	mux.HandleFunc("POST /v1/session/revoke", flow.RevokeSession)
	mux.HandleFunc("POST /v1/session/rotate", flow.RotateSession)
	mux.HandleFunc("GET /v1/users/{id}", userHandler.GetUserByID)
	mux.HandleFunc("PUT /v1/users/{id}", userHandler.UpdateUser)

	// question CRUD methods
	mux.HandleFunc("POST /v1/question", flow.DefinitionCommand(questionHandler.Create)) //👌
	mux.HandleFunc("GET /v1/plans/question/{plan_id}", questionHandler.GetQuestionByPlanId)
	mux.HandleFunc("PATCH /v1/question/{question_id}", flow.DefinitionCommand(questionHandler.UpdateQuestion))
	mux.HandleFunc("DELETE /v1/question/{question_id}", flow.DefinitionCommand(questionHandler.Delete))

	// invitation CRUD methods
	mux.HandleFunc("POST /v1/plans/{plan_id}/invites", invitationHandler.CreateInvitation)
	mux.HandleFunc("POST /v1/invites/{token}/join", invitationHandler.AcceptInvitation)

	// plan member CRUD methods
	mux.HandleFunc("POST /v1/plans/{plan_id}/members", flow.DefinitionCommand(planMemberHandler.AddMember))
	mux.HandleFunc("POST /v1/plans/{plan_id}/replace-member", flow.DefinitionCommand(flow.ReplaceGuest))
	mux.HandleFunc("GET /v1/plan_members/{plan_id}", planMemberHandler.ListMembers)
	mux.HandleFunc("PATCH /v1/members/{id}", flow.DefinitionCommand(planMemberHandler.UpdateMember))
	mux.HandleFunc("DELETE /v1/members/{id}", flow.DefinitionCommand(planMemberHandler.RemoveMember))
	mux.HandleFunc("DELETE /v1/plans/{plan_id}/members/{user_id}", flow.DefinitionCommand(planMemberHandler.RemoveMemberByPlanAndUser))

	// proposed activity CRUD methods
	mux.HandleFunc("POST /v1/proposed_activity/plans/{plan_id}", flow.DefinitionCommand(proposedActivityHandler.CreateActivity))
	mux.HandleFunc("GET /v1/proposed_activity/plans/{plan_id}", proposedActivityHandler.ListActivitiesByPlan)
	mux.HandleFunc("GET /v1/proposed_activity/{id}", proposedActivityHandler.GetActivityByID)
	mux.HandleFunc("PATCH /v1/proposed_activity/{id}", flow.DefinitionCommand(proposedActivityHandler.UpdateActivity))
	mux.HandleFunc("DELETE /v1/proposed_activity/{id}", flow.DefinitionCommand(proposedActivityHandler.DeleteActivity))

	// round CRUD methods
	mux.HandleFunc("GET /v1/rounds/{id}", planRoundHandler.GetRoundByID)
	mux.HandleFunc("PATCH /v1/rounds/{id}", flow.DefinitionCommand(planRoundHandler.UpdateRound))
	mux.HandleFunc("DELETE /v1/rounds/{id}", flow.DefinitionCommand(planRoundHandler.DeleteRound))
	mux.HandleFunc("POST /v1/rounds/open/{id}", flow.Publish)

	mux.HandleFunc("POST /internal/sessions/authorise", flow.Internal(flow.AuthoriseSession))
	mux.HandleFunc("GET /internal/rounds/{id}/option-snapshot", flow.Internal(flow.OptionSnapshot))
	mux.HandleFunc("GET /internal/rounds/{id}/selection", flow.Internal(flow.SelectionContext))

	flow.RegisterRoundRoutes(mux, planRoundHandler.CreateRound, planRoundHandler.ListRoundsByPlan)

	// selection CRUD methods
	mux.HandleFunc("POST /v1/confirmed-selection/plans/{plan_id}", func(w http.ResponseWriter, r *http.Request) {
		httpapi.Error(w, 409, "USE_ROUND_LIFECYCLE", "Confirm an eligible candidate through its round")
	})
	mux.HandleFunc("GET /v1/confirmed-selection/plans/{plan_id}", flow.GetPlanSelection)

	// start Server
	log.Println("Planning Service running on :8080...")
	server := &http.Server{Addr: ":8080", Handler: httpapi.Middleware(httpapi.Limits(flow.Guard(mux))), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 20 * time.Second, WriteTimeout: 30 * time.Second, IdleTimeout: 60 * time.Second}
	shutdown, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	go flow.Reconcile(shutdown)
	go func() {
		<-shutdown.Done()
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		server.Shutdown(ctx)
	}()
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("Server stopped: %v", err)
	}
}

func GetHealth(w http.ResponseWriter, r *http.Request) {
	result := JsonResponse{Status: "okay", Message: "service be alive"}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(result)
}
