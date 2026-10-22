package integration

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/google/uuid"
	"log"
	"time"
)

var errInvalidDefinition = errors.New("invalid definition")

func (h *Handler) completePublication(ctx context.Context, round Round) (Round, error) {
	if round.State == roundCollecting {
		return round, nil
	}
	var definition map[string]any
	if err := json.Unmarshal(round.Definition, &definition); err != nil {
		return round, err
	}
	if _, err := h.call(ctx, h.decision, "POST", "/internal/planning/validate", definition); err != nil {
		var remote RemoteError
		if errors.As(err, &remote) && remote.Status == 400 {
			h.rounds.abandonPublication(ctx, round.ID)
			return round, errInvalidDefinition
		}
		return round, err
	}
	payload, err := ProvisionPayload(round)
	if err != nil {
		return round, err
	}
	if _, err := h.call(ctx, h.participation, "POST", "/internal/rounds/provision", payload); err != nil {
		return round, err
	}
	return h.rounds.finalizePublication(ctx, round.ID)
}

func (h *Handler) completeFreeze(ctx context.Context, round Round) (Round, error) {
	if round.ResponseSnapshotID != "" {
		return round, nil
	}
	var snapshot struct {
		Roster []string `json:"roster"`
	}
	if err := json.Unmarshal(round.EvaluationSnapshot(), &snapshot); err != nil {
		return round, err
	}
	payload := map[string]any{"operationId": round.FreezeOperationID.String(), "roundId": round.ID.String(), "memberIds": snapshot.Roster, "requireComplete": !round.FreezeCountsRespondedOnly}
	if round.FreezeCountsRespondedOnly {
		payload["countRespondedOnly"] = true
	}
	if round.RosterPolicy == "close" {
		payload["optionSnapshotId"], payload["optionRevision"] = round.OptionSnapshotID.String(), round.OptionRevision
	}
	result, err := h.call(ctx, h.participation, "POST", "/internal/rounds/freeze", payload)
	if err != nil {
		var remote RemoteError
		if errors.As(err, &remote) && remote.Code == "RESPONSES_INCOMPLETE" {
			// Participation rejected before writing its snapshot. Restore admission
			// only for this exact attempted freeze; other failures remain retryable.
			if resetErr := h.rounds.cancelFreeze(ctx, round); resetErr != nil {
				return round, resetErr
			}
		}
		return round, err
	}
	id, ok := result["snapshotId"].(string)
	if !ok {
		return round, fmt.Errorf("invalid snapshot identity")
	}
	if _, err := uuid.Parse(id); err != nil {
		return round, err
	}
	return h.rounds.finalizeFreeze(ctx, round.ID, id)
}

// Any replica may reconcile the same command: Participation commands and local
// finalization are idempotent, and no database lock spans a network call.
func (h *Handler) Reconcile(ctx context.Context) {
	ticker := time.NewTicker(15 * time.Second)
	defer ticker.Stop()
	for {
		var pending []Round
		if err := h.db.WithContext(ctx).Where("state IN ?", []string{roundPublishing, roundLocking}).Order("id").Limit(10).Find(&pending).Error; err == nil {
			for _, round := range pending {
				callCtx, cancel := context.WithTimeout(ctx, 12*time.Second)
				var err error
				if round.State == roundPublishing {
					_, err = h.completePublication(callCtx, round)
				} else {
					_, err = h.completeFreeze(callCtx, round)
				}
				cancel()
				if err != nil {
					log.Printf("operation_pending round_id=%s stage=%s", round.ID, round.State)
				}
			}
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
