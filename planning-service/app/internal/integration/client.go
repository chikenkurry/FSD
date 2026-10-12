package integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type RemoteError struct {
	Status int
	Code   string
}

func (e RemoteError) Error() string { return fmt.Sprintf("upstream status %d: %s", e.Status, e.Code) }

func (h *Handler) call(ctx context.Context, base, method, path string, body any) (map[string]any, error) {
	encoded, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, method, strings.TrimRight(base, "/")+path, bytes.NewReader(encoded))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("x-internal-token", h.token)
	response, err := (&http.Client{Timeout: 180 * time.Second}).Do(req)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	payload, err := io.ReadAll(io.LimitReader(response.Body, 2_000_001))
	if err != nil || len(payload) > 2_000_000 {
		return nil, fmt.Errorf("invalid upstream response")
	}
	result := map[string]any{}
	if json.Unmarshal(payload, &result) != nil {
		return nil, fmt.Errorf("invalid upstream JSON")
	}
	if response.StatusCode >= 300 {
		code, _ := result["code"].(string)
		return nil, RemoteError{response.StatusCode, code}
	}
	return result, nil
}
