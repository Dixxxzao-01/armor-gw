// Package bandit: Thompson 采样策略学习（平移 Python 版 strategy_bandit 语义）
package bandit

import (
	"encoding/json"
	"math"
	"math/rand"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type arm struct {
	Wins   int `json:"w"`
	Losses int `json:"l"`
}

type Bandit struct {
	mu   sync.Mutex
	path string
	state map[string]map[string]*arm
	rng   *rand.Rand
	dirty  bool        // 脏标记：持久化节流
	lastFlush int64    // 上次落盘时间戳（秒）
}

func New(path string) *Bandit {
	b := &Bandit{path: path,
		state: make(map[string]map[string]*arm),
		rng:   rand.New(rand.NewSource(time.Now().UnixNano()))}
	b.load()
	return b
}

// Pick: Thompson 采样选族
func (b *Bandit) Pick(model string, families []string, exclude map[string]bool) string {
	b.mu.Lock()
	defer b.mu.Unlock()
	best, bestScore := "", -1.0
	for _, fam := range families {
		if exclude[fam] {
			continue
		}
		a := b.getArm(model, fam)
		w, l := float64(a.Wins), float64(a.Losses)
		score := betaSample(b.rng, w+1, l+1)
		if score > bestScore {
			bestScore, best = score, fam
		}
	}
	return best
}

// Feedback: 胜负回报
func (b *Bandit) Feedback(model, family string, win bool) {
	b.mu.Lock()
	defer b.mu.Unlock()
	a := b.getArm(model, family)
	if win {
		a.Wins++
	} else {
		a.Losses++
	}
	// 持久化节流：10s 内多次反馈只落一次盘（防高频 IO 持锁拖慢 Pick）
	now := time.Now().Unix()
	b.dirty = true
	if now-b.lastFlush >= 10 {
		b.lastFlush = now
		b.persistLocked()
	}
}

// SeedPrior: 探针画像注入先验
func (b *Bandit) SeedPrior(model, family string, score float64) {
	b.mu.Lock()
	defer b.mu.Unlock()
	a := b.getArm(model, family)
	a.Wins += int(score * 10)
	a.Losses += int((1 - score) * 10)
	b.dirty = true
	now := time.Now().Unix()
	if now-b.lastFlush >= 10 {
		b.lastFlush = now
		b.persistLocked()
	}
}

func (b *Bandit) getArm(model, family string) *arm {
	m, ok := b.state[model]
	if !ok {
		m = make(map[string]*arm)
		b.state[model] = m
	}
	a, ok := m[family]
	if !ok {
		a = &arm{}
		m[family] = a
	}
	return a
}

// Flush: 外部安全调用（补齐节流窗口内漏盘的终态——进程退出前调）
func (b *Bandit) Flush() {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.dirty {
		b.persistLocked()
		b.dirty = false
	}
}

func (b *Bandit) persistLocked() {
	if b.path == "" {
		return
	}
	_ = os.MkdirAll(filepath.Dir(b.path), 0o755)
	data, err := json.MarshalIndent(b.state, "", "  ")
	if err != nil {
		return
	}
	tmp := b.path + ".tmp"
	if os.WriteFile(tmp, data, 0o644) == nil {
		_ = os.Rename(tmp, b.path)
	}
}

func (b *Bandit) load() {
	if b.path == "" {
		return
	}
	data, err := os.ReadFile(b.path)
	if err != nil {
		return
	}
	_ = json.Unmarshal(data, &b.state)
}

// betaSample: Beta(α,β) 采样（Marsaglia-Tsang 两 gamma 法）
func betaSample(rng *rand.Rand, alpha, beta float64) float64 {
	x := gammaSample(rng, alpha)
	y := gammaSample(rng, beta)
	if x+y == 0 {
		return 0.5
	}
	return x / (x + y)
}

// gammaSample: Gamma(k,1)（Marsaglia-Tsang）
func gammaSample(rng *rand.Rand, k float64) float64 {
	if k < 1 {
		u := rng.Float64()
		return gammaSample(rng, k+1) * math.Pow(u, 1/k)
	}
	d := k - 1.0/3
	c := 1.0 / math.Sqrt(9*d)
	for {
		x := rng.NormFloat64()
		v := 1 + c*x
		if v <= 0 {
			continue
		}
		v = v * v * v
		u := rng.Float64()
		if u < 1-0.0331*x*x*x*x {
			return d * v
		}
		if math.Log(u) < 0.5*x*x+d*(1-v+math.Log(v)) {
			return d * v
		}
	}
}
