package integration

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"unicode/utf8"

	"planning-service/app/internal/model"

	"github.com/google/uuid"
)

type Settings struct {
	Currency         string           `json:"currency"`
	MinorDigits      *int             `json:"currency_minor_digits,omitempty"`
	CostScope        string           `json:"cost_scope"`
	Timezone         string           `json:"timezone"`
	ExecutionMode    string           `json:"execution_mode"`
	Criteria         []map[string]any `json:"criteria,omitempty"`
	ScenarioCosts    []map[string]any `json:"scenario_costs,omitempty"`
	Canonicalization map[string]any   `json:"canonicalization,omitempty"`
	GroupObjective   map[string]any   `json:"group_objective,omitempty"`
	// DecisionQuestion is the question members help answer; the plan title is used when empty.
	DecisionQuestion     string `json:"decision_question,omitempty"`
	InterpretationPolicy string `json:"interpretation_policy,omitempty"`
}

func BuildSnapshot(plan model.Plan, round model.PlanRound, id uuid.UUID, settings Settings) (map[string]any, error) {
	if len(plan.Members) == 0 || len(plan.Members) > 30 || len(plan.ProposedActivities) == 0 || len(plan.ProposedActivities) > 8 {
		return nil, fmt.Errorf("publish requires 1-30 members and 1-8 options")
	}
	question := strings.TrimSpace(settings.DecisionQuestion)
	if question == "" {
		question = plan.Title
	}
	if utf8.RuneCountInString(question) > 300 {
		return nil, fmt.Errorf("decision question exceeds 300 characters")
	}
	mode := settings.ExecutionMode
	if mode == "" {
		mode = "options"
	}
	digits := 2
	if settings.MinorDigits != nil {
		digits = *settings.MinorDigits
	}
	roster := make([]string, 0, len(plan.Members))
	for _, member := range plan.Members {
		roster = append(roster, member.UserID.String())
	}
	sort.Strings(roster)
	options := make([]map[string]any, 0, len(plan.ProposedActivities))
	candidates := []map[string]any{}
	for _, option := range plan.ProposedActivities {
		metadata := map[string]any{}
		if len(option.Metadata) > 0 && json.Unmarshal(option.Metadata, &metadata) != nil {
			return nil, fmt.Errorf("invalid option metadata")
		}
		facts := metadata["facts"]
		if facts == nil {
			facts = []any{}
		}
		description := ""
		if option.Description != nil {
			description = *option.Description
		}
		entry := map[string]any{"option_id": option.ID.String(), "title": option.Title, "description": description, "facts": facts, "identity": metadata["identity"]}
		// The brief is the organiser-reviewed web or AI overview shown to members.
		if brief, ok := metadata["brief"].(map[string]any); ok && len(encoded(brief)) <= 8000 {
			entry["brief"] = brief
		}
		options = append(options, entry)
		if entries, ok := metadata["candidates"].([]any); ok {
			for _, entry := range entries {
				c, ok := entry.(map[string]any)
				if !ok {
					return nil, fmt.Errorf("invalid scheduled candidate")
				}
				c["option_id"], c["activity_id"], c["currency"] = option.ID.String(), option.ID.String(), settings.Currency
				candidates = append(candidates, c)
			}
		}
	}
	sort.Slice(options, func(i, j int) bool { return options[i]["option_id"].(string) < options[j]["option_id"].(string) })
	sort.Slice(plan.Questions, func(i, j int) bool {
		if plan.Questions[i].SortOrder == plan.Questions[j].SortOrder {
			return plan.Questions[i].ID.String() < plan.Questions[j].ID.String()
		}
		return plan.Questions[i].SortOrder < plan.Questions[j].SortOrder
	})
	questions := make([]map[string]any, 0, len(plan.Questions))
	for _, q := range plan.Questions {
		metadata := map[string]any{}
		if len(q.Options) > 0 && json.Unmarshal(q.Options, &metadata) != nil {
			return nil, fmt.Errorf("invalid question metadata")
		}
		format := "text"
		switch q.Type {
		case model.QuestionTypeCustomSingleChoice:
			format = "choice"
		case model.QuestionTypeCustomMultiChoice:
			format = "multi_choice"
		}
		question := map[string]any{"question_id": q.ID.String(), "label": q.Title, "required": q.IsRequired, "answer_format": format}
		if choices, ok := metadata["options"]; ok {
			question["choices"] = choices
		}
		if definition, ok := metadata["decision"].(map[string]any); ok {
			for _, key := range []string{"role", "criterion", "relevance", "leader_weight", "numeric_intent", "mapping", "answer_format"} {
				if value, exists := definition[key]; exists {
					question[key] = value
				}
			}
		}
		questions = append(questions, question)
	}
	snapshot := map[string]any{"schema_version": "planning-snapshot-v1", "plan_id": plan.ID.String(), "round_id": round.ID.String(),
		"roster_policy": "close", "roster_is_final": false,
		"option_revision": round.RoundNumber, "option_snapshot_id": id.String(), "decision_question": question,
		"currency": settings.Currency, "currency_minor_digits": digits, "cost_scope": settings.CostScope,
		"timezone": settings.Timezone, "execution_mode": mode, "roster": roster, "options": options, "questions": questions,
		"execution_context": map[string]any{"candidates": candidates}}
	if round.SourceRoundID != nil {
		snapshot["previous_round_id"] = round.SourceRoundID.String()
	}
	if settings.InterpretationPolicy != "" {
		snapshot["interpretation_policy"] = settings.InterpretationPolicy
	}
	if settings.Criteria != nil {
		snapshot["criteria"] = settings.Criteria
	}
	if settings.ScenarioCosts != nil {
		snapshot["scenario_costs"] = settings.ScenarioCosts
	}
	if settings.Canonicalization != nil {
		snapshot["canonicalization"] = settings.Canonicalization
	}
	if settings.GroupObjective != nil {
		snapshot["group_objective"] = settings.GroupObjective
	}
	if len(encoded(snapshot)) > 1_500_000 {
		return nil, fmt.Errorf("published form exceeds snapshot size limit")
	}
	return snapshot, nil
}

func ProvisionPayload(round Round) (map[string]any, error) {
	snapshot := map[string]any{}
	if err := json.Unmarshal(round.Definition, &snapshot); err != nil {
		return nil, err
	}
	ids := []string{}
	for _, value := range snapshot["options"].([]any) {
		ids = append(ids, value.(map[string]any)["option_id"].(string))
	}
	questions := []map[string]any{}
	for _, value := range snapshot["questions"].([]any) {
		q := value.(map[string]any)
		choices := q["choices"]
		if choices == nil {
			choices = []any{}
		}
		questions = append(questions, map[string]any{"questionId": q["question_id"], "required": q["required"], "answerFormat": q["answer_format"], "choices": choices})
	}
	payload := map[string]any{"operationId": round.PublishOperationID.String(), "roundId": round.ID.String(), "planId": round.PlanID.String(),
		"optionRevision": round.OptionRevision, "optionSnapshotId": round.OptionSnapshotID.String(), "activityIds": ids,
		"memberIds": snapshot["roster"], "questions": questions, "currency": snapshot["currency"], "minorDigits": snapshot["currency_minor_digits"]}
	if round.RosterPolicy == "close" {
		payload["rosterPolicy"] = "close"
	}
	return payload, nil
}

func sameJSON(a, b []byte) bool {
	var left, right any
	if json.Unmarshal(a, &left) != nil || json.Unmarshal(b, &right) != nil {
		return false
	}
	return string(encoded(left)) == string(encoded(right))
}
