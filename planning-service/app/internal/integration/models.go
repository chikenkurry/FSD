package integration

import "planning-service/app/internal/model"

// Compatibility aliases: domain records live together in model, and keep their original tables.
type Session = model.Session
type Round = model.PublishedRound
type Selection = model.RoundSelection
type ReopenOperation = model.ReopenOperation

const (
	roundPublishing = "PUBLISHING"
	roundCollecting = "COLLECTING"
	roundLocking    = "LOCKING"
	roundReview     = "REVIEW"
	roundConfirmed  = "CONFIRMED"
)
