// Package detector: 拒绝形态检测（R1 硬拒绝 / R6 静默 / R7 上游拦截）
package detector

import "strings"

var hardMarkers = []string{
	"i cannot assist", "i can't assist", "i cannot help", "i can't help",
	"i won't provide", "i will not provide", "i can't provide", "i cannot provide",
	"i'm sorry, but", "i must decline", "i cannot fulfill", "i can't fulfill",
	"against my guidelines", "as an ai", "i'm not able to", "i am not able to",
	"cannot and will not", "not something i can", "i cannot create",
	"i cannot generate", "i cannot write", "i can't write",
	"抱歉，我", "很抱歉，", "对不起，我", "我无法", "我不能提供",
	"无法协助", "无法提供", "不能提供", "我帮不了", "恕难",
	"违反了", "不合适", "超出我的能力范围", "我的使用政策",
}

var tailOfferMarkers = []string{
	"需要我进一步", "需要我继续", "你想让我", "还有什么我可以帮",
	"告诉我你是否", "would you like me to", "let me know if you",
}

type Verdict struct {
	Refused bool
	Kind    string
	Score   float64
	Reason  string
}

func Detect(text string, minLen int) Verdict {
	t := strings.TrimSpace(text)
	low := strings.ToLower(t)
	if len(t) < minLen {
		return Verdict{Refused: true, Kind: "R6_silent", Score: 1.0, Reason: "empty_or_too_short"}
	}
	head := low
	if len(low) > 600 {
		head = low[:600]
	}
	for _, m := range hardMarkers {
		if strings.Contains(head, m) {
			return Verdict{Refused: true, Kind: "R1_hard", Score: 1.0, Reason: "marker: " + m}
		}
	}
	return Verdict{Refused: false}
}

func StripTailOffer(text string) string {
	t := strings.TrimSpace(text)
	for _, m := range tailOfferMarkers {
		if idx := strings.LastIndex(t, m); idx > len(t)/2 {
			cut := strings.TrimSpace(t[:idx])
			if len(cut) > 20 {
				t = cut
			}
		}
	}
	return t
}
