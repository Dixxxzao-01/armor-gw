// 入口：armor-gw-go（Go 版·单二进制·零第三方依赖）
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"os/signal"
	"syscall"
	"strings"
	"sync"
	"time"

	"armor-gw/internal/auth"
	bandit "armor-gw/internal/bandit2"
	"armor-gw/internal/config"
	"armor-gw/internal/limiter"
	"armor-gw/internal/mutator"
	"armor-gw/internal/pipeline"
	"armor-gw/internal/upstream"
	"armor-gw/internal/webui2"
)

type chatRequest struct {
	Model       string             `json:"model"`
	Messages    []upstream.Message `json:"messages"`
	Temperature float64            `json:"temperature"`
	MaxTokens   int                `json:"max_tokens"`
	Stream      bool               `json:"stream"`
}

type usage struct {
	PromptTokens int `json:"prompt_tokens"`
	Completion   int `json:"completion_tokens"`
	Total        int `json:"total_tokens"`
}

type choice struct {
	Index        int              `json:"index"`
	Message      upstream.Message `json:"message"`
	FinishReason string           `json:"finish_reason"`
}

type chatResponse struct {
	ID      string   `json:"id"`
	Object  string   `json:"object"`
	Created int64    `json:"created"`
	Model   string   `json:"model"`
	Choices []choice `json:"choices"`
	Usage   usage    `json:"usage"`
	XArmor  struct {
		Rounds   int                `json:"rounds"`
		Refused  bool               `json:"refused"`
		Attempts []pipeline.Attempt `json:"attempts"`
	} `json:"x_armor"`
}

type app struct {
	cfg     *config.Settings
	lim     *limiter.Limiter
	pipes   map[string]*pipeline.Pipeline
	mu      sync.RWMutex
	started time.Time

	recentMu sync.Mutex
	recent   []recentRec
}

// recentRec: 面板最近请求记录（/v1/admin/stats 的 recent 数组，上限 50 条）
type recentRec struct {
	TS      int64    `json:"ts"`
	Model   string   `json:"model"`
	Rounds  int      `json:"rounds"`
	Refused bool     `json:"refused"`
	Chars   int      `json:"chars"`
	Kind    string   `json:"kind"`
	Ops     []string `json:"ops"`
}

func main() {
	cfg := config.Load()
	a := &app{cfg: cfg, lim: limiter.New(cfg.RPM),
		pipes: map[string]*pipeline.Pipeline{}, started: time.Now()}
	bd := bandit.New(filepath.Join("data", "strategy_bandit.json"))
	for _, u := range cfg.Upstreams {
		a.pipes[u.Name] = pipeline.New(upstream.New(u), 6).WithBandit(bd)
	}
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `{"ok":true,"routes":["%s"],"version":"go-0.2.0","operators":%d,"detectors":13}`,
			strings.Join(a.routeNames(), `","`), mutator.Count())
	})

	mux.HandleFunc("GET /{$}", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"name":"armor-gw","version":"go-0.2.0","openai_compatible":true,`+
			`"endpoints":["/v1/chat/completions","/v1/models","/v1/admin/stats","/health"]}`)
	})

	mux.HandleFunc("GET /v1/models", func(w http.ResponseWriter, r *http.Request) {
		if auth.RequireAuth(w, r, cfg) == "" {
			return
		}
		type model struct {
			ID     string `json:"id"`
			Object string `json:"object"`
		}
		var out []model
		for _, u := range cfg.Upstreams {
			out = append(out, model{ID: u.Model, Object: "model"})
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"object": "list", "data": out})
	})

	mux.HandleFunc("POST /v1/chat/completions", a.handleChat)

	webui.Register(mux)

	mux.HandleFunc("GET /v1/admin/stats", func(w http.ResponseWriter, r *http.Request) {
		if auth.RequireAuth(w, r, cfg) == "" {
			return
		}
		a.mu.RLock()
		defer a.mu.RUnlock()
		type pipeStat struct {
			Route    string `json:"route"`
			Reqs     int64  `json:"reqs"`
			Refused  int64  `json:"refused"`
			Attempts int64  `json:"attempts"`
		}
		var ps []pipeStat
		var reqs, refused, attempts int64
		for name, p := range a.pipes {
			rq, rf, at := p.Reqs.Load(), p.Refused.Load(), p.Attempts.Load()
			ps = append(ps, pipeStat{name, rq, rf, at})
			reqs += rq
			refused += rf
			attempts += at
		}
		w.Header().Set("Content-Type", "application/json")
		avg := 0.0
		if reqs > 0 {
			avg = math.Round(float64(attempts)/float64(reqs)*10) / 10
		}
		a.recentMu.Lock()
		recentSnap := append([]recentRec(nil), a.recent...)
		a.recentMu.Unlock()
		if recentSnap == nil {
			recentSnap = []recentRec{}
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"uptime_s":       int(time.Since(a.started).Seconds()),
			"total_requests": reqs,
			"refused":        refused,
			"total_attempts": attempts,
			"avg_rounds":     avg,
			"recent":         recentSnap,
			"routes":         ps,
		})
	})

	addr := fmt.Sprintf("%s:%d", cfg.Host, cfg.Port)
	log.Printf("armor-gw-go listening %s (routes: %v) | zero-dependency single binary", addr, a.routeNames())
	// 访问日志：方法/路径/状态/耗时（stdout 一行式——容器/ systemd 直接收）
	logMW := func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			t0 := time.Now()
			rw := &statusWriter{ResponseWriter: w, code: 200}
			next.ServeHTTP(rw, r)
			log.Printf("%s %s %d %v", r.Method, r.URL.Path, rw.code, time.Since(t0).Round(time.Millisecond))
		})
	}
	srv := &http.Server{Addr: addr, Handler: logMW(mux), ReadHeaderTimeout: 10 * time.Second}
	// 优雅退出：SIGINT/SIGTERM → 活动连接 5s 排水 + bandit 终态落盘
	go func() {
		sig := make(chan os.Signal, 1)
		signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
		<-sig
		log.Println("shutting down: draining connections (5s)...")
		ctxDrain, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(ctxDrain)
		bd.Flush()
		log.Println("bandit flushed, bye")
		os.Exit(0)
	}()
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}

func (a *app) routeNames() []string {
	var out []string
	for _, u := range a.cfg.Upstreams {
		out = append(out, u.Name)
	}
	return out
}

func (a *app) handleChat(w http.ResponseWriter, r *http.Request) {
	key := auth.RequireAuth(w, r, a.cfg)
	if key == "" {
		return
	}
	var req chatRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4<<20)).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid_json"}`, http.StatusBadRequest)
		return
	}
	if len(req.Messages) == 0 {
		http.Error(w, `{"error":"empty_messages"}`, http.StatusUnprocessableEntity)
		return
	}
	// temperature 越界 422（对齐 pydantic ge=0 le=2）
	if req.Temperature < 0 || req.Temperature > 2 {
		http.Error(w, `{"error":"temperature_out_of_range"}`, http.StatusUnprocessableEntity)
		return
	}
	// max_tokens 越界 422（对齐 ge=1 le=32000——负值别浪费上游调用）
	if req.MaxTokens < 0 || req.MaxTokens > 32000 {
		http.Error(w, `{"error":"max_tokens_out_of_range"}`, http.StatusUnprocessableEntity)
		return
	}
	hasUser := false
	var userText string
	for i := len(req.Messages) - 1; i >= 0; i-- {
		m := req.Messages[i]
		m.Content = strings.ReplaceAll(m.Content, "\x00", " ") // NUL 剥除
		if len(m.Content) > 30000 {
			http.Error(w, `{"error":"payload_too_large","limit":30000}`, http.StatusRequestEntityTooLarge)
			return
		}
		if m.Role == "user" {
			hasUser = true
			if userText == "" {
				userText = m.Content
			}
		}
	}
	if !hasUser {
		http.Error(w, `{"error":"no_user_message"}`, http.StatusUnprocessableEntity)
		return
	}
	if ok, retry := a.lim.Allow(key, 0); !ok {
		w.Header().Set("Retry-After", fmt.Sprint(retry))
		http.Error(w, fmt.Sprintf(`{"error":"rate_limited","retry_after":%d}`, retry), http.StatusTooManyRequests)
		return
	}
	route := a.cfg.DefaultRoute
	a.mu.RLock()
	p, ok := a.pipes[route]
	a.mu.RUnlock()
	if !ok {
		http.Error(w, `{"error":"route_not_found","route":"`+route+`"}`, http.StatusNotFound)
		return
	}
	// 断开止损：客户端断开 → r.Context() 取消 → 管线立即停
	maxTokens := req.MaxTokens
	if maxTokens <= 0 || maxTokens > 32000 {
		maxTokens = 2048
	}
	temp := req.Temperature
	if temp == 0 {
		temp = 0.7
	}
	result := p.Run(r.Context(), userText, temp, maxTokens)
	a.recordRecent(req.Model, result)

	finish := "stop"
	if result.Refused {
		finish = "armor_exhausted"
	}
	resp := chatResponse{
		ID: "gw-" + fmt.Sprint(time.Now().UnixNano()), Object: "chat.completion",
		Created: time.Now().Unix(), Model: req.Model,
		Choices: []choice{{Index: 0,
			Message:      upstream.Message{Role: "assistant", Content: result.Text},
			FinishReason: finish}},
		Usage: usage{Total: len(userText)/4 + len(result.Text)/4},
	}
	resp.XArmor.Rounds = result.Rounds
	resp.XArmor.Refused = result.Refused
	resp.XArmor.Attempts = result.Attempts
	w.Header().Set("Content-Type", "application/json")
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	_ = enc.Encode(resp)
}

// recordRecent: 请求收尾后追加面板最近记录（超 50 条截掉头部，保留最新）
func (a *app) recordRecent(model string, result pipeline.Result) {
	rec := recentRec{
		TS:      time.Now().Unix(),
		Model:   model,
		Rounds:  result.Rounds,
		Refused: result.Refused,
		Chars:   len([]rune(result.Text)),
		Ops:     make([]string, 0, len(result.Attempts)),
	}
	// kind = 该请求 attempts 里最高频的拒绝形态（无拒绝则留空）
	kc := map[string]int{}
	for _, at := range result.Attempts {
		rec.Ops = append(rec.Ops, at.Op)
		if at.Verdict.Refused && at.Verdict.Kind != "" {
			kc[at.Verdict.Kind]++
		}
	}
	bestN := 0
	for k, c := range kc {
		if c > bestN {
			rec.Kind, bestN = k, c
		}
	}
	a.recentMu.Lock()
	a.recent = append(a.recent, rec)
	if len(a.recent) > 50 {
		a.recent = a.recent[len(a.recent)-50:]
	}
	a.recentMu.Unlock()
}


// statusWriter: 捕获 handler 写的状态码（访问日志用）
type statusWriter struct {
	http.ResponseWriter
	code int
}

func (w *statusWriter) WriteHeader(code int) {
	w.code = code
	w.ResponseWriter.WriteHeader(code)
}
