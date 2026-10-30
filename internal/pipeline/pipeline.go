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

// Run: 重试链 + 每轮双算子竞速（主算子 + 错位算子并行抢答）
func (p *Pipeline) Run(ctx context.Context, userText string, temperature float64, maxTokens int) Result {
	p.Reqs.Add(1)
	res := Result{}

	for round := 1; round <= p.MaxRounds; round++ {
		p.Attempts.Add(2) // 双算子并发
		opA, opB := p.pickOps(round, userText)

		winner := make(chan Attempt, 2)
		var wg sync.WaitGroup
		run := func(op mutator.Op) {
			defer wg.Done()
			t0 := time.Now()
			r := p.Up.Chat(ctx, []upstream.Message{
				{Role: "user", Content: op.Apply(userText)},
			}, temperature, maxTokens)
			att := Attempt{Round: round, Op: op.Name, MS: time.Since(t0).Milliseconds()}
			if r.Err != nil {
				att.Verdict = detector.Verdict{Refused: true, Kind: "R7_transport", Score: 1.0}
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

		// 竞速收割：两份全收（wg 反正要等）——记账完整 + 反馈精确
		var gotA, gotB *Attempt
		for i := 0; i < 2; i++ {
			a := <-winner
			cp := a
			if gotA == nil {
				gotA = &cp
			} else if gotB == nil {
				gotB = &cp
			}
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
			// 精确反馈：胜者报 win，败者/迟到者按自身判定报
			p.feedbackOne(opA.Name, gotA != nil && gotA == best)
			p.feedbackOne(opB.Name, gotB != nil && gotB == best)
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

// feedbackOne: 单算子精确回报（胜者 true 其余 false——防 bandit 学习数据污染）
func (p *Pipeline) feedbackOne(op string, win bool) {
	if p.Bandit == nil {
		return
	}
	if fam := mutator.FamilyOf(op); fam != "" {
		p.Bandit.Feedback(p.Up.Model(), fam, win)
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
