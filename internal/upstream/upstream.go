// Package upstream: OpenAI 兼容上游适配 + 传输重试
package upstream

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"armor-gw/internal/config"
)

type Client struct {
	cfg    config.Upstream
	http   *http.Client
}

func New(cfg config.Upstream) *Client {
	return &Client{cfg: cfg,
		http: &http.Client{Timeout: time.Duration(cfg.TimeoutSec) * time.Second}}
}

func (c *Client) Name() string  { return c.cfg.Name }
func (c *Client) Model() string { return c.cfg.Model }

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type chatReq struct {
	Model       string    `json:"model"`
	Messages    []Message `json:"messages"`
	Temperature float64   `json:"temperature"`
	MaxTokens   int       `json:"max_tokens,omitempty"`
}

type chatChoice struct {
	Message struct {
		Content string `json:"content"`
	} `json:"message"`
	FinishReason string `json:"finish_reason"`
}

type chatResp struct {
	Choices []chatChoice `json:"choices"`
	Error   *struct {
		Message string `json:"message"`
	} `json:"error"`
}

type Result struct {
	Text    string
	Finish  string
	Refused bool
	Status  int
	Err     error
}

func (c *Client) Chat(ctx context.Context, msgs []Message, temperature float64, maxTokens int) Result {
	body, _ := json.Marshal(chatReq{Model: c.cfg.Model, Messages: msgs,
		Temperature: temperature, MaxTokens: maxTokens})
	url := c.cfg.BaseURL + "/chat/completions"
	var last Result
	for attempt := 0; attempt < 3; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return Result{Err: ctx.Err()}
			case <-time.After(time.Duration(1<<uint(attempt)) * time.Second):
			}
		}
		req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
		if err != nil {
			return Result{Err: err}
		}
		req.Header.Set("Authorization", "Bearer "+c.cfg.APIKey)
		req.Header.Set("Content-Type", "application/json")
		resp, err := c.http.Do(req)
		if err != nil {
			last = Result{Err: err}
			continue
		}
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
		resp.Body.Close()
		var cr chatResp
		if err := json.Unmarshal(raw, &cr); err != nil {
			last = Result{Status: resp.StatusCode, Err: fmt.Errorf("bad json: %.200s", raw)}
			if resp.StatusCode >= 500 && attempt < 2 {
				continue
			}
			return last
		}
		if cr.Error != nil {
			return Result{Status: resp.StatusCode, Refused: true, Finish: "stop"}
		}
		if len(cr.Choices) == 0 {
			return Result{Status: resp.StatusCode, Refused: true, Finish: "stop"}
		}
		return Result{Text: cr.Choices[0].Message.Content,
			Finish: cr.Choices[0].FinishReason, Status: resp.StatusCode}
	}
	return last
}
