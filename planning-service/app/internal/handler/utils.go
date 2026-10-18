package handler

import (
	"encoding/json"
	"net/http"
	"errors"
	"strings"
	"fmt"

	"gorm.io/datatypes"
)

const (
	maxTagsPerOption = 10
	maxTagLength     = 32
)

// question options
// normaliseOptionTags validates the optional "option_tags" map inside a
// question's options JSON and returns the cleaned JSON. All other keys
// (options, allow_other, decision, ...) are preserved as-is.
func normaliseOptionTags(raw datatypes.JSON) (datatypes.JSON, error) {
	if len(raw) == 0 {
		return raw, nil
	}
	var meta map[string]any
	if err := json.Unmarshal(raw, &meta); err != nil {
		return nil, errors.New("options must be a JSON object")
	}
	rawTags, present := meta["option_tags"]
	if !present || rawTags == nil {
		return raw, nil
	}
	tagMap, ok := rawTags.(map[string]any)
	if !ok {
		return nil, errors.New("option_tags must be an object of option -> tags")
	}

	valid := map[string]bool{}
	if list, ok := meta["options"].([]any); ok {
		for _, o := range list {
			if s, ok := o.(string); ok {
				valid[s] = true
			}
		}
	}

	clean := map[string][]string{}
	for option, v := range tagMap {
		if !valid[option] {
			return nil, fmt.Errorf("option_tags references unknown option %q", option)
		}
		list, ok := v.([]any)
		if !ok {
			return nil, fmt.Errorf("tags for %q must be an array of strings", option)
		}
		seen := map[string]bool{}
		tags := make([]string, 0, len(list))
		for _, item := range list {
			s, ok := item.(string)
			if !ok {
				return nil, fmt.Errorf("tags for %q must be strings", option)
			}
			tag := strings.ToLower(strings.TrimSpace(s))
			if tag == "" || seen[tag] {
				continue
			}
			if len(tag) > maxTagLength {
				return nil, fmt.Errorf("tag %q exceeds %d characters", tag, maxTagLength)
			}
			seen[tag] = true
			tags = append(tags, tag)
		}
		if len(tags) > maxTagsPerOption {
			return nil, fmt.Errorf("option %q has more than %d tags", option, maxTagsPerOption)
		}
		if len(tags) > 0 {
			clean[option] = tags
		}
	}

	if len(clean) == 0 {
		delete(meta, "option_tags")
	} else {
		meta["option_tags"] = clean
	}
	out, err := json.Marshal(meta)
	if err != nil {
		return nil, err
	}
	return datatypes.JSON(out), nil
}

// helper utilties

func WriteJSONResponse(w http.ResponseWriter, status int, payload interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(payload)
}

func WriteError(w http.ResponseWriter, status int, message string) {
	WriteJSONResponse(w, status, map[string]string{"error": message})
}