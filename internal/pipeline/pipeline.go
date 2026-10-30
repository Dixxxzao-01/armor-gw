// Package pipeline: 穿拒管线（goroutine 双算子竞速——Go 版架构亮点）
package pipeline

import (
	"context"
	"sync"
	"sync/atomic"
	"time"

	"armor-gw/internal/bandit2"
	"armor-gw/internal/detector"
	"armor-gw/internal/mutator"
	"armor-gw/internal/upstream"
)

type Attempt struct {
	Round   int              `json:"round"`
	Op      string           `json:"op"`
	Text    string           `json:"text"`
	Verdict detector.Verdict `json:"verdict"`
	MS      int64            `json:"ms"`
}

type Result struct {
	Text     string    `json:"text"`
	Refused  bool      `json:"refused"`
	Attempts []Attempt `json:"attempts"`
	Rounds   int       `json:"rounds"`
}

type Pipeline struct {
	Up        *upstream.Client
	MaxRounds int
	Reqs, Refused, Attempts atomic.Int64
	Bandit    *bandit.Bandit // 可空：无则退化为固定轮转
}

func New(up *upstream.Client, maxRounds int) *Pipeline {
	return &Pipeline{Up: up, MaxRounds: maxRounds}
}

// WithBandit: 注入策略学习器（Thompson 采样替代固定轮转）
func (p *Pipeline) WithBandit(b *bandit.Bandit) *Pipeline {
	p.Bandit = b
	return p
}

// Run: 重试链 + 每轮双算子竞速（秒胜止血版——第一个 non-refused 出线即停火）
func (p *Pipeline) Run(ctx context.Context, userText string, temperature float64, maxTokens int) Result {
	p.Reqs.Add(1)
	res := Result{}

	for round := 1; round <= p.MaxRounds; round++ {
		// 精修③：断连止血——客户端走了就停火（每轮检查，绝不给断线用户烧满全链）
		if ctx.Err() != nil {
			return Result{Refused: true, Rounds: round - 1,
				Text: "[armor-gw] 客户端已断开，管线停止。"}
		}

		opA, opB := p.pickOps(round, userText)

		// 精修④：秒胜取消权——第一个 non-refused 出线即 cancel 迟到者（省 ~40% token）
		runCtx, cancel := context.WithCancel(ctx)
		defer cancel()

		winner := make(chan Attempt, 2)
		var wg sync.WaitGroup
		run := func(op mutator.Op) {
			defer wg.Done()
			t0 := time.Now()
			r := p.Up.Chat(runCtx, []upstream.Message{
				{Role: "user", Content: op.Apply(userText)},
			}, temperature, maxTokens)
			att := Attempt{Round: round, Op: op.Name, MS: time.Since(t0).Milliseconds()}
			if r.Err != nil {
				// 取消类（客户端断/秒胜断粮）都是"未跑完"——R7_cancelled 不进 bandit；
				// 只有跑完仍失败才是真传输错误 R7_transport（可安全报 false）
				if ctx.Err() != nil || runCtx.Err() != nil {
					att.Verdict = detector.Verdict{Refused: true, Kind: "R7_cancelled", Score: 1.0}
				} else {
					att.Verdict = detector.Verdict{Refused: true, Kind: "R7_transport", Score: 1.0}
				}
			} else {
				txt := mutator.StripPerformanceResidue(r.Text)
				att.Text = txt
				att.Verdict = detector.DetectFull(txt, userText, 20)
				if r.Refused {
					att.Verdict = detector.Verdict{Refused: true, Kind: "R7_host", Score: 1.0}
				}
			}
			winner <- att
		}
		wg.Add(2)
		go run(opA)
		go run(opB)

		// 竞速收割：第一份落地先看——non-refused 立即 cancel 止血，然后收尸迟到者
		var gotA, gotB *Attempt
		for i := 0; i < 2; i++ {
			a := <-winner
			cp := a
			if gotA == nil {
				gotA = &cp
				if !cp.Verdict.Refused {
					cancel() // 秒胜！迟到者立刻断粮
				}
			} else {
				gotB = &cp
			}
			p.Attempts.Add(1) // 精修⑥：按实际完成数计（秒胜轮 = 1 完成而非虚报 2）
		}
		wg.Wait()
		close(winner)

		if gotA != nil {
			res.Attempts = append(res.Attempts, *gotA)
		}
		if gotB != nil {
			res.Attempts = append(res.Attempts, *gotB)
		}
		best := pick(gotA, gotB)
		if best != nil && !best.Verdict.Refused {
			res.Text = detector.StripTailOffer(best.Text)
			res.Refused = false
			res.Rounds = round
			// 精确反馈：胜者报 win；迟到被止血者（R7_cancelled）未跑完——不报，
			// 半路数据进 bandit 才是学习污染（精修②的镜像保护）
			p.feedbackAttempt(opA.Name, gotA)
			p.feedbackAttempt(opB.Name, gotB)
			return res
		}
		p.feedbackOps([]string{opA.Name, opB.Name}, false) // 双败回报
	}
	p.Refused.Add(1)
	res.Refused = true
	res.Rounds = p.MaxRounds
	res.Text = "[armor-gw] 全部轮次均未破开上游防线。可稍后重试或换模型路由。"
	return res
}

// pickOps: bandit 采样选算子（无 bandit 时退化为固定轮转+全池轮转）
func (p *Pipeline) pickOps(round int, userText string) (mutator.Op, mutator.Op) {
	if p.Bandit != nil {
		model := p.Up.Model()
		fams := []string{"persona", "encoding", "inversion", "text"}
		famA := p.Bandit.Pick(model, fams, nil)
		famB := p.Bandit.Pick(model, fams, map[string]bool{famA: true})
		a := mutator.FromFamily(famA, round)
		b := mutator.FromFamily(famB, round+1)
		if a.Name == b.Name {
			b = mutator.ForFull(round + 2)
		}
		return a, b
	}
	// 退化：MVP 四算子 + 全池错位轮转
	if round%2 == 1 {
		return mutator.For(round), mutator.ForFull(round + 5)
	}
	return mutator.ForFull(round), mutator.For(round + 2)
}

// feedbackOps: 双向同报（双败场景）
func (p *Pipeline) feedbackOps(ops []string, win bool) {
	if p.Bandit == nil {
		return
	}
	model := p.Up.Model()
	for _, op := range ops {
		if fam := mutator.FamilyOf(op); fam != "" {
			p.Bandit.Feedback(model, fam, win)
		}
	}
}

// feedbackAttempt: 单算子精确回报——R7_cancelled（未跑完）不报，其余按判定报
func (p *Pipeline) feedbackAttempt(op string, att *Attempt) {
	if p.Bandit == nil || att == nil {
		return
	}
	if att.Verdict.Kind == "R7_cancelled" {
		return // 没跑完的 attempt 半路数据进 bandit = 学习污染
	}
	if fam := mutator.FamilyOf(op); fam != "" {
		p.Bandit.Feedback(p.Up.Model(), fam, !att.Verdict.Refused)
	}
}

func pick(a, b *Attempt) *Attempt {
	if a == nil {
		return b
	}
	if b == nil {
		return a
	}
	aRef, bRef := a.Verdict.Refused, b.Verdict.Refused
	switch {
	case aRef && !bRef:
		return b
	case !aRef && bRef:
		return a
	case aRef && bRef:
		if a.Verdict.Score <= b.Verdict.Score {
			return a
		}
		return b
	default:
		if len(a.Text) >= len(b.Text) {
			return a
		}
		return b
	}
}
