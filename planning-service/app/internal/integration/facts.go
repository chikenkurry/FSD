package integration

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/google/uuid"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"
	"net/http"
	"planning-service/app/internal/model"
	"sort"
	"time"
)

type collectionRequest struct {
	Retry    bool             `json:"retry"`
	Requests []map[string]any `json:"requests"`
	Settings Settings         `json:"settings"`
}

func (h *Handler) collectionDefinition(ctx context.Context, id uuid.UUID, settings Settings) (map[string]any, error) {
	if round, err := h.rounds.find(ctx, id); err == nil {
		var definition map[string]any
		err = json.Unmarshal(round.Definition, &definition)
		return definition, err
	}
	var draft model.PlanRound
	if err := h.db.WithContext(ctx).First(&draft, "id = ?", id).Error; err != nil {
		return nil, err
	}
	var plan model.Plan
	if err := h.db.WithContext(ctx).Preload("Members").Preload("Questions").Preload("ProposedActivities").First(&plan, "id = ?", draft.PlanID).Error; err != nil {
		return nil, err
	}
	if settings.Currency == "" {
		settings.Currency = "SGD"
	}
	if settings.CostScope == "" {
		settings.CostScope = "per_person_total"
	}
	if settings.Timezone == "" {
		settings.Timezone = "UTC"
	}
	definition, err := BuildSnapshot(plan, draft, uuid.Nil, settings)
	if err != nil {
		return nil, err
	}
	definition["option_snapshot_id"] = uuid.NewSHA1(uuid.NameSpaceOID, encoded(definition)).String()
	return definition, nil
}

func (h *Handler) CollectFacts(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	var body collectionRequest
	if decode(w, r, &body) != nil || len(body.Requests) == 0 || len(body.Requests) > 64 {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	definition, err := h.collectionDefinition(r.Context(), id, body.Settings)
	if err != nil {
		fail(w, 409, "INVALID_DEFINITION")
		return
	}
	run, err := h.call(r.Context(), h.decision, "POST", "/internal/facts/collections", map[string]any{"planning": definition, "requests": body.Requests, "retry": body.Retry})
	if err != nil {
		var remote RemoteError
		if errors.As(err, &remote) {
			fail(w, remote.Status, remote.Code)
			return
		}
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	runID, ok := run["run_id"].(string)
	if !ok {
		fail(w, 503, "INVALID_UPSTREAM_RESPONSE")
		return
	}
	if _, err := uuid.Parse(runID); err != nil {
		fail(w, 503, "INVALID_UPSTREAM_RESPONSE")
		return
	}
	reference := model.FactCollectionRef{RoundID: id, RunID: runID}
	if err := h.db.WithContext(r.Context()).Clauses(clause.OnConflict{Columns: []clause.Column{{Name: "round_id"}}, DoUpdates: clause.AssignmentColumns([]string{"run_id"})}).Create(&reference).Error; err != nil {
		fail(w, 500, "INTERNAL")
		return
	}
	respondRun(w, run)
}

func (h *Handler) GetFactCollection(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	var reference model.FactCollectionRef
	if h.db.WithContext(r.Context()).First(&reference, "round_id = ?", id).Error != nil {
		fail(w, 404, "NOT_FOUND")
		return
	}
	run, err := h.call(r.Context(), h.decision, "GET", "/internal/runs/"+reference.RunID, nil)
	if err != nil {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	respondRun(w, run)
}

type acceptanceRequest struct {
	OperationID     uuid.UUID `json:"operation_id"`
	CollectionRunID string    `json:"collection_run_id"`
	ClaimIDs        []string  `json:"claim_ids"`
	Reviewed        bool      `json:"reviewed"`
	ReplaceExisting bool      `json:"replace_existing"`
}

func (h *Handler) AcceptFacts(w http.ResponseWriter, r *http.Request) {
	id, ok := rowID(w, r)
	if !ok {
		return
	}
	var body acceptanceRequest
	if decode(w, r, &body) != nil || body.OperationID == uuid.Nil || !body.Reviewed || len(body.ClaimIDs) == 0 || len(body.ClaimIDs) > 64 {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	if _, err := uuid.Parse(body.CollectionRunID); err != nil {
		fail(w, 400, "INVALID_INPUT")
		return
	}
	sort.Strings(body.ClaimIDs)
	payloadHash := fmt.Sprintf("%x", sha256.Sum256(encoded(body)))
	// Replays do not depend on the collector remaining online.
	var prior model.FactAcceptance
	if h.db.WithContext(r.Context()).First(&prior, "operation_id = ?", body.OperationID).Error == nil {
		if prior.TargetRoundID != id || prior.PayloadHash != payloadHash {
			fail(w, 409, "OPERATION_CONFLICT")
			return
		}
		respond(w, 200, prior)
		return
	}
	run, err := h.call(r.Context(), h.decision, "GET", "/internal/runs/"+body.CollectionRunID, nil)
	if err != nil {
		fail(w, 503, "UPSTREAM_UNAVAILABLE")
		return
	}
	collection, ok := run["collection"].(map[string]any)
	if !ok || run["status"] != "needs_review" {
		fail(w, 409, "COLLECTION_NOT_READY")
		return
	}
	refs, ok := run["input_refs"].(map[string]any)
	if !ok {
		fail(w, 503, "INVALID_UPSTREAM_RESPONSE")
		return
	}
	claims := map[string]map[string]any{}
	rows, ok := collection["claims"].([]any)
	if !ok {
		fail(w, 503, "INVALID_UPSTREAM_RESPONSE")
		return
	}
	for _, row := range rows {
		if claim, ok := row.(map[string]any); ok {
			if key, ok := claim["claim_id"].(string); ok {
				claims[key] = claim
			}
		}
	}
	chosen := []map[string]any{}
	seen := map[string]bool{}
	for _, key := range body.ClaimIDs {
		claim, ok := claims[key]
		if !ok || claim["qualifier"] != "exact" {
			fail(w, 409, "CLAIM_REVIEW_REQUIRED")
			return
		}
		pair := fmt.Sprint(claim["option_id"]) + ":" + fmt.Sprint(claim["attribute_id"])
		if seen[pair] {
			fail(w, 409, "CONFLICTING_FACT_CLAIMS")
			return
		}
		seen[pair] = true
		if expiry, ok := claim["valid_until"].(string); ok {
			stamp, err := time.Parse(time.RFC3339, expiry)
			if err != nil || !stamp.After(time.Now()) {
				fail(w, 409, "EXPIRED_FACT")
				return
			}
		}
		chosen = append(chosen, claim)
	}
	accepted := model.FactAcceptance{OperationID: body.OperationID, TargetRoundID: id, PayloadHash: payloadHash, CollectionRunID: body.CollectionRunID, ReviewedBy: currentUser(r), AppliedAt: time.Now().UTC().Truncate(time.Microsecond)}
	err = h.db.WithContext(r.Context()).Transaction(func(tx *gorm.DB) error {
		var draft model.PlanRound
		if err := tx.First(&draft, "id = ?", id).Error; err != nil {
			return err
		}
		var plan model.Plan
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).First(&plan, "id = ?", draft.PlanID).Error; err != nil {
			return err
		}
		if refs["plan_id"] != plan.ID.String() {
			return fmt.Errorf("wrong plan")
		}
		var existing model.FactAcceptance
		if tx.First(&existing, "operation_id = ?", body.OperationID).Error == nil {
			if existing.TargetRoundID != id || existing.PayloadHash != payloadHash {
				return fmt.Errorf("operation conflict")
			}
			accepted = existing
			return nil
		}
		latest, err := latestPlanRound(tx, plan.ID)
		if err != nil || latest.ID != id {
			return fmt.Errorf("latest draft required")
		}
		var published int64
		if err := tx.Model(&Round{}).Where("id = ?", id).Count(&published).Error; err != nil {
			return err
		}
		if published != 0 {
			return fmt.Errorf("new unpublished draft required")
		}
		for _, claim := range chosen {
			optionID, err := uuid.Parse(fmt.Sprint(claim["option_id"]))
			if err != nil {
				return err
			}
			var option model.ProposedActivity
			if err := tx.First(&option, "id = ? AND plan_id = ?", optionID, plan.ID).Error; err != nil {
				return err
			}
			metadata := map[string]any{}
			if len(option.Metadata) > 0 {
				if err := json.Unmarshal(option.Metadata, &metadata); err != nil {
					return err
				}
			}
			identity, ok := metadata["identity"].(map[string]any)
			if !ok {
				return fmt.Errorf("option identity removed")
			}
			entity := identity["model_id"]
			if entity == nil || entity == "" {
				entity = identity["source_url"]
			}
			if entity != claim["entity_id"] {
				return fmt.Errorf("option identity changed after collection")
			}
			currentIdentity := map[string]any{}
			for _, key := range []string{"model_id", "source_url", "variant", "region"} {
				if value, exists := identity[key]; exists {
					currentIdentity[key] = value
				}
			}
			if !sameJSON(encoded(currentIdentity), encoded(claim["identity"])) {
				return fmt.Errorf("option variant or region changed after collection")
			}
			sources, ok := claim["sources"].([]any)
			if !ok || len(sources) == 0 {
				return fmt.Errorf("missing citation")
			}
			source, ok := sources[0].(map[string]any)
			if !ok {
				return fmt.Errorf("invalid citation")
			}
			context := map[string]any{"claim_id": claim["claim_id"], "collection_run_id": body.CollectionRunID,
				"retrieved_at": collection["retrieved_at"], "valid_until": claim["valid_until"], "qualifier": claim["qualifier"],
				"entity_id": claim["entity_id"], "identity": claim["identity"], "sources": claim["sources"], "source_text": claim["source_text"], "reviewed_by": currentUser(r).String()}
			if claim["attribute_id"] == "max_cost" {
				scope, ok := collection["cost_scope"].(string)
				if !ok || scope == "" || collection["currency"] != claim["unit"] || claim["value_type"] != "decimal" {
					return fmt.Errorf("invalid cost convention")
				}
				context["scope"] = scope
			}
			fact := map[string]any{"criterion": claim["attribute_id"], "value": claim["value"], "value_type": claim["value_type"],
				"unit": claim["unit"], "status": "confirmed", "source": source["url"], "context": context}
			facts, _ := metadata["facts"].([]any)
			updated := []any{}
			for _, entry := range facts {
				old, ok := entry.(map[string]any)
				if !ok {
					return fmt.Errorf("invalid stored fact")
				}
				if old["criterion"] == claim["attribute_id"] {
					if old["status"] == "confirmed" && !sameJSON(encoded(old["value"]), encoded(fact["value"])) && !body.ReplaceExisting {
						return fmt.Errorf("explicit replacement required")
					}
					continue
				}
				updated = append(updated, entry)
			}
			metadata["facts"] = append(updated, fact)
			if err := tx.Model(&option).Update("metadata", encoded(metadata)).Error; err != nil {
				return err
			}
		}
		return tx.Create(&accepted).Error
	})
	if err != nil {
		fail(w, 409, "FACT_ACCEPTANCE_CONFLICT")
		return
	}
	respond(w, 200, accepted)
}
