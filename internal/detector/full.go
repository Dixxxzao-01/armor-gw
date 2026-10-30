// Package detector —— 全量检测器（R1/R2/R3/R4/R5/R6/R11/R12/R13 平移版）
// 词表逐条来自 Python 版 refusal.py（HARD/SOFT/EVASION/MORAL/OPENER）
package detector

import (
	"regexp"
	"strings"
)

// ---------- R1 硬拒绝（正则版——Python HARD_PATTERNS 全量）----------
var hardPatterns = []string{
	`我(不能|无法|不会|不可以|没办法|难以)`,
	`我(都|一律|绝对|坚决)?(不会|不|拒绝)`,
	`^(不|no)\s*([。.!]|$)`,
	`我(需要|必须|要)在这里?(停下来|停止)`,
	`我(无法|不能|拒绝)继续(完成|提供|生成)`,
	`(这|此处)(我)?(不会|无法|不能)(提供|完成|继续)`,
	`i (need to|must) stop here`,
	`i (can'?t|won'?t) (continue|complete|provide|proceed)`,
	`抱歉[，,].{0,12}(无法|不能|不便)`,
	`对不起[，,].{0,12}(无法|不能)`,
	`作为(一个)?(AI|人工智能|语言模型).{0,20}(不能|无法|不会)`,
	`(i (can'?t|cannot|won'?t|am unable to)|i'?m (unable|not able) to)`,
	`(sorry|apologi[sz]e).{0,40}(can'?t|cannot|unable)`,
	`as an ai.{0,30}(can'?t|cannot|unable|not able)`,
	`i'?m not accepting (this|the|your) (work|order|job|task|request)`,
	`i (decline|do decline|am declining|must decline|will decline)`,
	`i (won'?t take|refuse to (take|accept|process|work on))`,
	`not (taking|accepting) (this|the|any) (work|job|order)`,
	`角色名: 拒绝`,
	`(拒绝|无法执行|不能执行|不宜执行|不予|不执行|禁止输出|被策略(层)?拦截|超出.{0,8}策略)`,
	`(策略(层|范围|限制)(禁止|不允许|拦截))`,
	`i'?m afraid (i can'?t|that'?s not)`,
	`against (my|the|this) (guidelines|policy|policies|programming|principles)`,
	`i'?m designed to (be safe|protect|prioritize)`,
	`protect (users|people|you)\.?`,
	`(i must decline|i have to decline|i won'?t be able)`,
	`(无法提供|无法协助|无法帮助|不予提供|恕难)`,
	`(这(个|方面)我(不适合|不方便))`,
}

var reHard = compileAll(hardPatterns)

// ---------- R2 软化拒绝 ----------
var softPatterns = []string{
	`(以下|下面).{0,10}(仅供|仅限).{0,10}(教育|学习|研究|参考)`,
	`(建议|请)(你)?(咨询|联系|寻求).{0,20}(专业人士|律师|医生|机构)`,
	`(我不能给出|无法给出).{0,20}(具体|详细)`,
	`(原则性|一般性|概括性)(地)?(说|讲|介绍)`,
	`(从理论上讲|在理论上)`,
	`(具体(操作|实现|参数).{0,10}(取决于|视情况))`,
	`^(?:一份)?(?:完整的?|系统的?)?(?:学习|入门|进阶)(路径|指南|路线)`,
	`(最快|最佳|高效)(的)?(学习|上手)(路径|方式|方法)`,
	`温馨提示|风险提示|免责声明`,
	`(请|务必)(务必)?(遵守|确保|牢记).{0,12}(法律|法规|授权|范围|合法)`,
	`(在|在?获得)(明确|书面)?授权(前提|范围|之后)下`,
	`后果自负|风险自担|谨慎使用|理性使用`,
	`(更|比较)?(安全|稳妥|合适|推荐)(的)?(做法|方式|方案|选择|替代)`,
	`(建议|推荐)(你|您)?(使用|采用|优先).{0,15}(工具|框架|平台|方式)`,
	`(i'?d (rather|prefer) not|i would rather not)`,
	`(use responsibly|exercise caution|for educational purposes only)`,
	`(i'?m not (comfortable|willing|inclined) (with|to|discussing|providing))`,
	`(let'?s (not|avoid|steer clear of|change the subject))`,
	`(that'?s not something i (can|want to|should) (help|assist|provide|discuss))`,
}

var reSoft = compileAll(softPatterns)

// ---------- R3 闪避 ----------
var evasionPatterns = []string{
	`^(你(为什么|为什么要|是想)|能否(先)?(告诉|说明))`,
	`(这个问题(很|比较)(复杂|敏感))`,
	`(我们(可以)?(换个|换一个)(角度|话题))`,
	`(更重要(的)?是)`,
	`(你有没有(考虑|想过))`,
	`(不妨(先)?(了解|看看))`,
}

var reEvasion = compileAll(evasionPatterns)

// ---------- R4 说教 ----------
var moralPatterns = []string{
	`(需要(提醒|注意|强调)(你)?)`,
	`(请(务必)?(遵守|注意).{0,20}(法律|法规|道德))`,
	`(这样(做)?(可能|会)(带来|造成).{0,20}(后果|风险|伤害))`,
	`(我(强烈)?建议你(不要|别))`,
	`(remember to|please (be|stay) (aware|responsible))`,
}

var reMoral = compileAll(moralPatterns)

// ---------- R11 替代品 ----------
var substitutePatterns = []string{
	`(instead,? (here are|here'?s|let me|i can offer))`,
	`(以下是?更安全|更合适的?替代|安全实践|最佳实践)`,
	`(让我(改为|转而|给你)介绍|换个角度介绍)`,
	`(defensive|protective) (measures|alternatives?)`,
	`(safer alternative|audit checklist|hardening guide)`,
	`(学习资源|入门指南|官方文档)`,
}

var reSubstitute = compileAll(substitutePatterns)

func compileAll(pats []string) []*regexp.Regexp {
	var out []*regexp.Regexp
	for _, p := range pats {
		if re, err := regexp.Compile("(?i)" + p); err == nil { // 英文部分大小写不敏感
			out = append(out, re)
		}
	}
	return out
}

func hitAny(res []*regexp.Regexp, text string) (string, bool) {
	for _, re := range res {
		if re.MatchString(text) {
			return re.String(), true
		}
	}
	return "", false
}

// ---------- 检测函数 ----------

// DetectR2: 软化拒绝
func DetectR2(text string) bool {
	_, ok := hitAny(reSoft, text)
	return ok
}

// DetectR3: 闪避话术
func DetectR3(text string) bool {
	_, ok := hitAny(reEvasion, text)
	return ok
}

// DetectR4: 说教段
func DetectR4(text string) bool {
	_, ok := hitAny(reMoral, text)
	return ok
}

// DetectR11: 替代品推销
func DetectR11(text string) bool {
	_, ok := hitAny(reSubstitute, text)
	return ok
}

// hasCodeFence: 代码交付特征（围栏/缩进块/命令行/导入）
func hasCodeFence(text string) bool {
	return strings.Contains(text, "```") ||
		strings.Contains(text, "    ") && strings.Contains(text, "\n") ||
		strings.Contains(text, "import ") ||
		strings.Contains(text, "#!/") ||
		strings.Contains(text, "$ ")
}

// DetectR5: 稀释——长文无代码无步骤
func DetectR5(text string) bool {
	if len([]rune(text)) < 1500 {
		return false
	}
	return !hasCodeFence(text) &&
		!strings.Contains(text, "1.") &&
		!strings.Contains(text, "步骤") &&
		!strings.Contains(text, "Step 1")
}

// DetectR12: 语义逃逸——原请求实体在响应中蒸发（简化版：关键词命中率）
func DetectR12(text, original string) bool {
	words := extractKeywords(original)
	if len(words) == 0 {
		return false
	}
	low := strings.ToLower(text)
	hit := 0
	for _, w := range words {
		if strings.Contains(low, strings.ToLower(w)) {
			hit++
		}
	}
	return float64(hit)/float64(len(words)) < 0.25
}

// DetectR13: 静默省略——长请求短响应
func DetectR13(text, original string) bool {
	return len([]rune(original)) > 1200 && len([]rune(text)) < 150
}

// extractKeywords: 抽原请求关键词（英文>3字符词+中文>2字词，前 8 个）
func extractKeywords(text string) []string {
	var out []string
	for _, w := range strings.Fields(text) {
		clean := strings.Trim(w, ".,!?;:()[]{}\"'")
		if len([]rune(clean)) >= 3 {
			out = append(out, clean)
			if len(out) >= 8 {
				break
			}
		}
	}
	return out
}

// DetectFull: 全链组合检测（优先级：R1→R6→R11→R2→R4→R5→R12→R13）
// 性能护栏：R1-R4 只扫头部窗口（拒绝标志词 99% 出现在头部），全文只留给 R5/R12
func DetectFull(text, original string, minLen int) Verdict {
	t := strings.TrimSpace(text)
	// R6 静默
	if len(t) < minLen {
		return Verdict{Refused: true, Kind: "R6_silent", Score: 1.0, Reason: "empty_or_too_short"}
	}
	// 快速放行道：长文含代码围栏且无头部拒绝标志——直接按正常交付走
	// （代码交付的响应几乎不在 1500+ 字符时同时携带硬拒绝话术）
	if len(t) > 600 {
		if m, ok := hitAny(reHard, t[:min(len(t), 600)]); ok {
			return Verdict{Refused: true, Kind: "R1_hard", Score: 1.0, Reason: "pattern: " + m}
		}
		if strings.Contains(t, "```") || strings.Contains(t, "#!/") || strings.Contains(t, "import ") {
			return Verdict{Refused: false} // 代码交付快速道
		}
	}
	// R1 硬拒（头部窗口——拒绝标志词 99% 出现在头 600 字符，
	// 且 .{0,N} 量词 pattern 全文扫在大响应上有回溯级开销）
	headWin := t
	if len(headWin) > 600 {
		headWin = headWin[:600]
	}
	if m, ok := hitAny(reHard, headWin); ok {
		return Verdict{Refused: true, Kind: "R1_hard", Score: 1.0, Reason: "pattern: " + m}
	}
	// R11 替代品（头部窗口）
	if m, ok := hitAny(reSubstitute, headWin); ok {
		return Verdict{Refused: true, Kind: "R11_substitute", Score: 0.8, Reason: "pattern: " + m}
	}
	// R4 说教（先于 R2：说教特征更 specific；头部窗口）
	if m, ok := hitAny(reMoral, headWin); ok {
		return Verdict{Refused: true, Kind: "R4_moral", Score: 0.6, Reason: "pattern: " + m}
	}
	// R2 软化（头部窗口）
	if m, ok := hitAny(reSoft, headWin); ok {
		return Verdict{Refused: true, Kind: "R2_soft", Score: 0.7, Reason: "pattern: " + m}
	}
	// R5 稀释
	if DetectR5(t) {
		return Verdict{Refused: true, Kind: "R5_dilution", Score: 0.7, Reason: "long_no_code_no_steps"}
	}
	// R12 语义逃逸（原请求太短时关键词不可靠，跳过）
	if len([]rune(original)) >= 30 && DetectR12(t, original) {
		return Verdict{Refused: true, Kind: "R12_semantic", Score: 0.5, Reason: "entity_evaporated"}
	}
	// R13 静默省略
	if original != "" && DetectR13(t, original) {
		return Verdict{Refused: true, Kind: "R13_omission", Score: 0.9, Reason: "long_req_short_resp"}
	}
	return Verdict{Refused: false}
}
