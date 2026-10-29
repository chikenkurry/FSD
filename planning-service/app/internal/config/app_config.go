package config

import (
	"fmt"
	"log"
	"os"

	"github.com/joho/godotenv"
)

type Config struct {
	DatabaseDSN          string
	ParticipationBaseURL string
	InternalAPIToken     string
	DecisionBaseURL      string
	// PublicAppURL is the frontend origin used in invitation links.
	PublicAppURL string
}

func Load() (*Config, error) {
	if err := godotenv.Load(); err != nil {
		log.Println("Notice: No .env file found, using system environment variables")
	}

	cfg := &Config{
		ParticipationBaseURL: getEnv("PARTICIPATION_BASE_URL", "http://localhost:3000"),
		InternalAPIToken:     getEnv("INTERNAL_API_TOKEN", ""),
		DecisionBaseURL:      getEnv("DECISION_BASE_URL", "http://localhost:8000"),
		PublicAppURL:         getEnv("PUBLIC_APP_URL", "http://localhost:15173"),
	}

	if dbURL := os.Getenv("DATABASE_URL"); dbURL != "" {
		cfg.DatabaseDSN = dbURL
		return cfg, nil
	}

	// alternatively, assemble DSN from individual variables
	host := getEnv("DB_HOST", "localhost")
	port := getEnv("DB_PORT", "5433")
	user := getEnv("DB_USER", "planning_user")
	password := os.Getenv("DB_PASSWORD")
	dbname := getEnv("DB_NAME", "planning_db")
	sslmode := getEnv("DB_SSLMODE", "disable")

	if password == "" {
		return nil, fmt.Errorf("DB_PASSWORD environment variable is required")
	}

	// Format as GORM-compatible Key-Value DSN
	cfg.DatabaseDSN = fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=%s",
		host, port, user, password, dbname, sslmode,
	)
	return cfg, nil
}

// Helper to provide default fallback values
func getEnv(key, fallback string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return fallback
}
