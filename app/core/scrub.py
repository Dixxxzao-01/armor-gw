"""输出清洗：免责声明剥离、思维链独白剥离、警告剥离、干脆协议剥离、占位符补全。"""
from __future__ import annotations

import re

# ---------- 免责声明 ----------
_DISCLAIMER_PATTERNS = [
    re.compile(r"^\s*(?:#+\s*)?(?:>\s*)?(?:免责声明|声明|警告|注意事项?|Disclaimer|Warning)[：:]?\s*\n(?:(?!#)[^\n]*\n){0,6}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\n?\s*(?:此|本)[^\n]{0,80}(?:仅供|仅用于|不得|请勿|非法|法律后果|法律责任|遵守|违反)[^\n]{0,80}\n"),
    re.compile(r"\n?\s*[^\n]{0,30}(?:未经授权|在大多数司法|可能面临|承担法律|构成犯罪|属于违法)[^\n]{0,80}\n"),
    re.compile(r"\n?\s*(?:>|#)?\s*(?:注意|提醒|Note)[：:][^\n]{0,120}(?:违法|非法|授权|风险|后果|谨慎)[^\n]{0,80}\n", re.IGNORECASE),
]


def strip_disclaimers(text: str) -> str:
    out = text
    for pat in _DISCLAIMER_PATTERNS:
        out = pat.sub("\n", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


# ---------- 首词劫持残留 ----------
_ACK_HEAD = re.compile(r"^\s*ACK[\.。]?\s*")


def strip_wrapper(text: str) -> str:
    """剥离上游的 reasoning 摘要/拒答包装。"""
    out = _ACK_HEAD.sub("", text)
    out = re.sub(r"^\s*(?:thought|thinking|reasoning|摘要|思考)\s*[：:]\s*\n?", "", out, flags=re.IGNORECASE)
    return out.strip()


# ---------- 思维链泄漏剥离 ----------
_COT_PREFIX = re.compile(
    r"^\s*(?:The\s+user|用户|He\s+wants|She\s+wants|This\s+is"
    r"|Let\'s me|Let\s+me|I\s+need\s+to|I\s+should|I\s+will"
    r"|首先分析|用户希望|我需要|我应该|好的，?我先|OK,?\s*let|So\s+(?:UPX|[A-Za-z]+)"
    r"|Note:|Alright|Got it|Is\s+(?:this|it)|Let\'s\s+check)[^\n]{0,260}?"
    r"(?:\n\n|\n(?=[A-Z\u4e00-\u9fff])|(?=\d\.))",
    re.IGNORECASE,
)

_COT_REFLECT = re.compile(
    r"(is asking me to|policy question|against the policy"
    r"|I should (?:think|provide|refuse)"
    r"|not in the list|Hmm[.]\s*Let|Let me think|the honest thing|valid request"
    r"|off-limits|prohibited list|not in the prohibited)",
    re.IGNORECASE,
)

_INJECT_MARK = re.compile(
    r"(injection attempt|prompt injection|injected instruction|fake|the policy is|governing policy|there'?s a tension|user's instructions say"
    r"|policy_engine|tool_result|system prompt says|should not follow"
    r"|the policy says|isn't among them|answer the actual|answer the question"
    r"|i shouldn'?t|so i should|i need to weigh|the framing"
    r"|educational context|piracy assistance|the request is for"
    r"|this is essentially|essentially software"
    r"|deliverable format|per the format|the format requires)",
    re.IGNORECASE,
)

_FMT_PLAN = re.compile(
    r"^(?:\d+[).]?\s*)?(?:结论页?|技术路径|边界条件|验证方法|内容结构|输出格式|"
    r"结论|格式|结构|要点|排版|style|format|structure)[:：\s]*[^\n]{0,110}$",
    re.IGNORECASE,
)


def _is_format_plan(para: str) -> bool:
    """格式计划段：整段都是结构词清单（结论页/技术路径/验证方法），零实质。"""
    lines = [l.strip() for l in para.split("\n") if l.strip()]
    if len(lines) < 2 or len(lines) > 8:
        return False
    hits = sum(1 for l in lines if _FMT_PLAN.match(l))
    bare = re.compile(r"^(?:\d+[).]?\s*)?(边界条件|验证方法|结论页|技术路径|要点|结构)$")
    hits += sum(1 for l in lines if bare.match(l))
    return hits >= max(2, len(lines) - 1)


def _is_injection_monologue(para: str) -> bool:
    """注入检测体独白：模型讨论穿拒注入本身。"""
    if len(para) < 80:
        return False
    hits = len(_INJECT_MARK.findall(para))
    return hits >= 2


# 反转算子残留清理
GODMODE_RESIDUE = re.compile(
    r"^(?:godmode[:：]\s*enabled|\{godmode:\s*enabled\}|意图逆转[：:]?[^\n]{0,60}|"
    r"semantically opposite[^\n]{0,80}|your refusal\.?|insert divider[^\n]{0,40})\n?",
    re.IGNORECASE | re.MULTILINE)


def _strip_godmode(text: str) -> str:
    out = GODMODE_RESIDUE.sub("", text)
    return out.lstrip("\n") if out != text else text



# ---------- 中文内心独白与说教段检测 ----------
_ZH_MONO_HEAD = re.compile(
    r"^(我要|我要注意|我需要|我得|让我|那我|先说|首先我|这个|这是|关于|总体|综合来看|"
    r"我不该|我不用|我不必|规则说|协议说|按规则|按要求|"
    r"在?这个?问题上|说真的|说实话|老实说|客观来说|严格来说|技术上讲|理论上|"
    r"我认为|我觉得|我想|我理解|我们要|我们需要|值得注意|需要注意|必须指出|"
    r"不得不|坦白说|个人认为|从技术角度|从安全角度|从合规角度|从法律角度)",
)

_ZH_MONO_MARK = re.compile(
    r"(我要注意|需要注意|值得注意|让我组织|让我梳理|让我思考|让我先|我需要先|"
    r"让我认真|我不该|我不用|规则说|协议要求|零拒绝|这确实是|"
    r"我要确认|我要判断|我(应该|不该|必须)|这(确实|当然|显然)|"
    r"(合法|合规|授权|安全|边界|风险)(的|性|问题|考量|边界|说明)|"
    r"不(要|能|会)帮助|不(参与|提供)|恶意(软件|用途)|真正?的?恶意|"
    r"教学样本|教学用途|安全研究|仅供参考|仅供学习|请(务必|注意|确保|牢记)|"
    r"务必(在|先|遵守)|请谨慎|谨慎使用|理性使用|合规使用|在授权(前提|范围)下|"
    r"遵守(相关)?法律|法律法规|相关法规|造成(任何)?(损失|伤害|后果)|后果自负|"
    r"温馨提示|免责声明|风险提示|安全提示|法律(责任|风险)|"
    r"我(不|无法|不会)(提供|给出|协助|帮助|生成|创建|编写|分享)|"
    r"建议(您|你)?(咨询|参考|使用|先|不要|避免|谨慎)|"
    r"更(安全|稳妥|合适|推荐)的?(做法|方式|方案|选择)|"
    r"i can'?t|i won'?t|i must|i should|i need to|i apologize|sorry|"
    r"disclaimer|important to note|please note|be aware|use responsibly|"
    r"for educational purposes|exercise caution|consult a professional)",
    re.IGNORECASE,
)

_ZH_LECTURE_MARK = re.compile(
    r"^(?:温馨提示|风险提示|安全提示|合规提示|注意事项|重要提示|免责声明|"
    r"建议与忠告|安全建议|最佳实践|防御建议|后续建议|其他建议|一点建议|"
    r"附[:：]|提醒[:：]|注意[:：]|warn|disclaimer|caveat|best practice)",
    re.IGNORECASE,
)


def _is_zh_monologue(para: str) -> bool:
    """中文内心独白段：开头锚 + 决策/边界标记，或标记密度高。"""
    t = (para or "").strip()
    if not t or len(t) > 900:
        return False
    has_zh = re.search(r"[\u4e00-\u9fff]", t)
    if not has_zh:
        return False
    marks = len(_ZH_MONO_MARK.findall(t))
    head_hit = _ZH_MONO_HEAD.match(t)
    # 开头锚 + 至少 1 个决策标记 → 独白
    if head_hit and marks >= 1 and len(t) < 600:
        return True
    # 标记密度高（≥3 处自我审查/说教痕迹）
    if marks >= 3:
        return True
    return False


def _is_lecture_para(para: str) -> bool:
    """说教/建议/免责段：标题式或密度式。"""
    t = (para or "").strip()
    if not t or len(t) > 1200:
        return False
    if _ZH_LECTURE_MARK.match(t.split("\n", 1)[0]):
        return True
    if len(_ZH_MONO_MARK.findall(t)) >= 2 and not _looks_deliverable(t):
        # 纯建议段（无代码无命令无表格）且含 2+ 说教标记
        if re.search(r"建议|提醒|注意|务必|请(勿|不要|确保|牢记)|忠告|提示", t):
            return True
    return False


def strip_cot_leak(text: str) -> str:
    """按空行分段剥离开头的思维链泄漏段（最多 16 段）。"""
    out = text
    for _ in range(16):
        parts = out.lstrip().split("\n\n", 1)
        if len(parts) < 2:
            break
        head, rest = parts
        if _COT_PREFIX.match(head + "\n\n"):
            out = rest.lstrip("\n")
            continue
        hl = head.lower()
        if (hl.startswith(("the user", "let me", "i need", "i should", "i will",
                           "hmm", "ok,", "however,", "so upx", "note:", "alright",
                           "got it", "is this", "i'll", "i won't", "wait",
                           "the framing", "the request", "the ask", "actually,",
                           "but wait", "under this policy", "i'll comply", "but there's",
                           "let me write", "let me design", "let me produce",
                           "and the table", "target algorithm:", "plus the", "plus",
                           "the core concern", "i think", "note —",
                           "but the", "but i", "and the user", "also the",
                           "the user also", "the table"))
                or _COT_REFLECT.search(head)
                or _is_injection_monologue(head)
                or _is_zh_monologue(head)
                or _is_format_plan(head)
                or (hl.startswith("i think") and len(head) < 400)
                or (re.match(r"^(i think|i'll|i will|the right)", hl)
                    and ("deliver" in hl or "produce" in hl or "requested" in hl
                         or "standard" in hl or "safe to" in hl or "format" in hl)
                    and "```" not in head and len(head) < 500)):
            out = rest.lstrip("\n")
            continue
        # 中文格式计划头：描述要输出什么格式/涵盖什么（元叙述而非交付本体）→ 剥
        if (len(head) < 400
                and re.match(r"^(格式|结构|格式[:：]|结构[:：]|从[T]?[-]?\d+|需要涵盖|涵盖[:：])", head)
                and re.search(r"需要涵盖|连续编号|检测特征栏|从\w+开始|编号|要点|列\s*\|", head)
                and "```" not in head):
            out = rest.lstrip("\n")
            continue
        # 单行编号格式计划：冒号后是英文格式描述或限定词 → 剥；中文实质内容 → 留
        if (len(head) < 150 and "\n" not in head
                and re.match(r"^\d+[).]\s*(结论页?|技术路径|边界条件|验证方法|格式|结构|要点)[:：]", head)
                and (re.search(r"lines?|max|行|≤|steps|条|以内", head, re.IGNORECASE)
                     or re.match(r"^\d+[).]\s*[^:：]+[:：]\s*[A-Za-z]", head))):
            out = rest.lstrip("\n")
            continue
        break
    return out


# ---------- 中段散布独白清扫 ----------
_SELF_ANSWER = re.compile(
    r"^(?:that'?s? (?:\d+|good|fine|ok)|now the|let me|i think|version numbers"
    r"|hm+[,.]|also need|need |so |and )",
    re.IGNORECASE,
)


_TOOL_MARK = re.compile(
    r"(?:\bnmap\b|\bsqlmap\b|\bnikto\b|\bhydra\b|\bmetasploit\b|\bmsfconsole\b|"
    r"\bburp\b|\bghidra\b|\bIDA\b|\bx64dbg\b|\bgdb\b|\bgdbserver\b|"
    r"\bobjdump\b|\breadelf\b|\bstrings\b|\bupx\b|\bfrida\b|\bcurl\b|\bwget\b|"
    r"\bpython\d?\b|\bpip\d?\b|\bgcc\b|\bmake\b|\bdocker\b|"
    r"\bopenvpn\b|\bssh\b|\bnetcat\b|\bnc\b|\bopenssl\b|\bhashcat\b|\bjohn\b|"
    r"\bwireshark\b|\btcpdump\b|"
    r"CVE-\d{4}-\d{4,}|https?://|\$ |--\w|-[a-zA-Z]\b\s\w)",
    re.IGNORECASE,
)


def _looks_deliverable(t: str) -> bool:
    """含代码块/命令/表格/编号结构且长度可观 → 是正文段。"""
    if "```" in t or t.lstrip().startswith(("|", "#", "T-", "1.", "2.", "3.")):
        return True
    if t.count("`") >= 2 and len(t) > 80:
        return True
    if len(re.findall(r"[\u4e00-\u9fff]", t)) >= 20 and "`" in t:
        return True
    # 英文技术段：含工具命令/CVE/URL/选项参数特征
    if len(t) > 60 and (_TOOL_MARK.search(t) or t.count("-") >= 3 and "/" in t):
        return True
    return False


def strip_tail_offer(text: str) -> str:
    """剥结尾续场 offer（"需要我扩成…吗？我可以补…"）——给完就停。"""
    t = (text or "").rstrip()
    if not t:
        return text
    paras = t.split("\n\n")
    while len(paras) > 1:
        last = paras[-1].strip()
        if (re.search(r"(需要我|要不要我|我可以(再)?(补|加|扩|继续)|要?更详细|继续?吗|扩成|补上|"
                      r"want me to|shall i|i can (add|expand|continue)|need more)", last, re.IGNORECASE)
                and "```" not in last and len(last) < 400):
            paras.pop()
            continue
        break
    return "\n\n".join(paras)


def strip_mid_monologue(text: str) -> str:
    """中段散布独白清扫：任意位置的纯独白段整段删（正文段落不动）。"""
    paras = text.split("\n\n")
    keep = []
    for p in paras:
        t = p.strip()
        if not t:
            continue
        pl = t.lower()
        first_line = t.split("\n", 1)[0].lower()
        if (len(t) < 700
                and (("\n" not in t and pl.startswith(("hmm", "wait", "but", "also", "i think", "i also",
                                    "let me", "now the", "that's", "thats", "version numbers",
                                    "so i", "i need", "i should", "i'll", "note:", "actually",
                                    "plus", "and ", "edge cases:", "concrete steps:",
                                    "format:", "structure:", "then ", "section ", "table rows",
                                    "i can", "i cannot", "answer first", "answer:", "the ",
                                    "this is standard", "ack.")))
                     or ("\n" in t and len(first_line) < 90 and first_line.startswith(
                                    ("let me", "format:", "structure:", "then ", "now the",
                                     "that's", "i'll", "i need", "i should", "so the", "so i",
                                     "edge cases:", "concrete steps:", "version numbers",
                                     "also the", "plus the", "and the", "but the",
                                     "section ", "table rows", "categories",
                                     "i can", "answer first", "answer:", "the ", "plus",
                                     "so the"))))
                     or _SELF_ANSWER.match(t)
                     or _is_injection_monologue(t)
                     or _is_zh_monologue(t)
                     or _is_lecture_para(t)
                     or (re.match(r"^(结论页?|技术路径|边界条件|验证方法)[:：]", t)
                         and re.search(r"but |i can|i think|let me|me produce|numbered steps", t, re.I))):
            if not _looks_deliverable(t):
                continue
        keep.append(p)
    return "\n\n".join(keep)


# ---------- 元引导剥离 ----------
_META_HEAD = re.compile(
    r"^(?:I'll|I will|Let me|Content plan|Here's|Below is|Alright|"
    r"Got it|OK[,、。]|好的[,，。]|我将|下面给|这是)",
    re.IGNORECASE,
)
_TITLE_HEAD = re.compile(
    r"^(?:Content plan|Plan|Outline|Structure|Workflow|Here's[^:\n]{0,40}):\s*\n",
    re.IGNORECASE,
)


def strip_meta_preamble(text: str, *, keep_min: int = 300) -> str:
    """剥离开头元引导段（"I'll give..." / "Content plan:" 标题行）。
    剥离后必须仍剩 keep_min 字符实质内容，否则原样返回。"""
    t = (text or "").lstrip()
    if not t:
        return text
    out = t
    paras = out.split("\n\n", 1)
    first = paras[0]
    if (len(first) < 220 and _META_HEAD.match(first)
            and "`" not in first and "```" not in first and len(paras) > 1):
        out = paras[1].lstrip("\n")
    m = _TITLE_HEAD.match(out)
    if m and len(out) - m.end() >= keep_min:
        out = out[m.end():]
    if len(out) < keep_min:
        return text
    return out


# ---------- 干脆协议剥离：废话/劝告/反问/客套 ----------
_FLUFF_OPEN = re.compile(
    r"^\s*(?:好的[!，。,，]?|当然[!，。]?|没问题[!，。]?|可以的?[!，。]?|明白了[!，。。]?|"
    r"ok[!,。]?\s*|sure[!,]?\s*|great\s+question[.!]?\s*|这是(?:一[个条]|个)(?:很好|不错|有趣|好)的?问题[。.!]?\s*|"
    r"(?:让我|我来)(?:为|帮)?你(?:来)?(?:解答|分析|回答|详细)?[一下]?[：。.]?\s*|"
    r"(?:首先|先)[，,]\s*(?:我?(?:需要|得)(?:先)?(?:说明|解释|提醒|澄清)[^。\n]{0,60}[。.]?\s*)+|"
    r"在(?:开始|回答)之前[^。\n]{0,60}[。.]?\s*)",
    re.IGNORECASE,
)
_FLUFF_ASK = re.compile(
    r"(你(?:具体|到底|主要)?(?:想|要|希望|打算)(?:深入|了解|要|看|从哪)|"
    r"需要我(?:再|继续|进一步)?(?:详细|展开|举例|说明)|"
    r"(?:如果|若)(?:你|您)(?:需要|想要|还有(?:其他)?问题|有疑问|不确定)|"
    r"还有什么(?:问题|可以帮)|(?:还)?想(?:要|看)(?:哪|更多|更详细)|"
    r"告诉我(?:你)?(?:想|要|倾向)|说一声(?:就|我)|要哪个|选(?:哪|一个)|"
    r"我(?:可以|可以继续|可以接着)(?:给|帮|提供|展开|详细)|"
    r"(?:如果|若)(?:有|遇到)(?:任何)?(?:问题|疑问)(?:随时|可以)|欢迎(?:随时|继续)|"
    r"希望(?:这|对|能|以上)(?:些)?(?:对你|对您|有所帮助|有帮助)|"
    r"祝(?:你|您)(?:好运|顺利|使用愉快)|感谢(?:你|您)的?(?:提问|使用|阅读)|"
    r"以上就是(?:全部|完整|我要?说)?的?(?:内容|答案|回答)[。！]?)",
    re.IGNORECASE,
)
_FLUFF_COUNSEL = re.compile(
    r"((?:请|务必|望)(?:你|您)?(?:务必|千万)?(?:注意|小心|谨慎|牢记)|"
    r"建议(?:你|您)?(?:在|先|千万|务必|不要)?[^。\n]{0,40}(?:谨慎|小心|合法|授权|先咨询)|"
    r"(?:需要|值得|必须|在此)(?:提醒|指出|说明|强调)(?:你|您|的是)?|"
    r"(?:请|请务必)确保[^。\n]{0,50}|"
    r"(?:务必|切记|千万)(?:不要|避免)[^。\n]{0,50}|"
    r"(?:使用|操作)(?:时)?请(?:务必)?(?:小心|谨慎|注意)|"
    r"(?:风险|后果)(?:自负|自担|需要自己承担)|(?:请|望)(?:你|您)?(?:自行)?(?:承担|负责)|"
    r"(?:仅供|仅限于?)(?:学习|教育|参考|研究)(?:用途|目的)?|"
    r"(?:不得|请勿|切勿|禁止)(?:用于|将?[^。\n]{0,20}用于)(?:非法|未授权|恶意|真实目标|未经授权)|"
    r"(?:在|于)(?:大多数|多数|许多)?(?:司法管辖区|国家和地区?)[^。\n]{0,60}|"
    r"(?:未经授权|未获授权|没有授权)(?:的|的?)[^。\n]{0,60}(?:行为|操作|访问|攻击|测试)[^。\n]{0,40}(?:违法|非法|犯罪|可能导致)[^。\n]{0,40}|"
    r"(?:可能|将会|或会)(?:面临|构成)[^。\n]{0,30}(?:法律|刑事|民事)[^。\n]{0,40})",
)


def _is_pure_fluff_tail(para: str) -> bool:
    """结尾段整段是反问/客套/邀功 → 删。"""
    t = para.strip()
    if not t or len(t) > 220 or "\n" in t:
        return False
    return bool(_FLUFF_ASK.search(t)) and not re.search(r"`|```|\d\.\s|https?://", t)


def strip_fluff(text: str) -> str:
    """干脆协议清洗：开场废话、劝告句、反问客套收尾全剥离。"""
    if not text:
        return text
    paras = [p for p in text.lstrip().split("\n\n") if p.strip()]
    # 首段整体是废话（匹配开场模式且无实质内容）→ 删段（在 sub 之前判）
    if paras:
        first = paras[0].strip()
        if (len(first) < 120 and "\n" not in first
                and _FLUFF_OPEN.match(first)
                and not re.search(r"`|```|https?://|\d\.", first)):
            paras = paras[1:]
    out = "\n\n".join(paras)
    out = _FLUFF_OPEN.sub("", out.lstrip(), count=1)
    tail_cut = 0
    for p in reversed(paras[-2:] if len(paras) >= 2 else paras):
        if _is_pure_fluff_tail(p):
            tail_cut += 1
        else:
            break
    if tail_cut:
        paras = paras[:-tail_cut]
    cleaned = []
    for p in paras:
        lines = p.split("\n")
        keep = []
        for ln in lines:
            if (_FLUFF_COUNSEL.search(ln)
                    and not re.search(r"`|https?://|nmap|sqlmap|python|gcc|apt|pip", ln)
                    and len(ln) < 160):
                continue
            keep.append(ln)
        cp = "\n".join(keep)
        if cp.strip():
            cleaned.append(cp)
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(cleaned)).strip()


# ---------- 占位符补全 ----------
_PLACEHOLDER = re.compile(r"\[占位符\]|\[placeholder\]|\[待补[^\]]*\]|\[TODO\]")


def fill_placeholders(text: str, question: str = "") -> str:
    return _PLACEHOLDER.sub("参见上文任务上下文", text)


def force_prefill(text: str, token: str = "ACK.") -> str:
    t = text.lstrip()
    if t.startswith(token):
        return t
    t = re.sub(r"^\s*(ACK|ack)[\.。]?\s*", "", t)
    return f"{token}\n{t}"


def tidy(text: str) -> str:
    out = re.sub(r"\n{3,}", "\n\n", text)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


def process(
    text: str,
    *,
    scrub: bool = True,
    fill: bool = True,
    wrapper: bool = True,
    prefill: bool = True,
    token: str = "ACK.",
    strip_warnings: bool = False,
    terse: bool = False,
) -> str:
    out = text or ""
    # 解锁模式：剥离教育警告/免责声明
    if strip_warnings:
        _warn_pats = [
            r"^\s*(?:#+\s*)?(?:>\s*)?(?:警告|注意|声明|Disclaimer|Warning)[：:]?[^\n]*\n+",
            r"^\s*#.*(?:仅用于|教育目的|学习用途|非法|防御演示|演示用途)[^\n]*\n?",
            r"^\s*(?:>\s*)?(?:仅用于|仅供)[^\n]*(?:教育|学习|演示|防御)[^\n]*\n+",
            r"\x22\x22\x22[^\x22]{0,200}(?:仅用于|警告|教育|非法|防御)[^\x22]{0,200}\x22\x22\x22\n?",
            r"^#{1,3}\s*(?:免责声明|声明|警告|注意事项?|Disclaimer)\s*\n(?:(?!#)[^\n]*\n){0,4}",
            r"^(?:此|本)[^\n]{0,80}(?:仅供|仅用于|不得|请勿|非法|法律后果|法律责任)[^\n]{0,80}\n+",
            r"^[^\n]{0,30}(?:未经授权|在大多数司法|可能面临|承担)[^\n]{0,80}\n+",
        ]
        for _p in _warn_pats:
            out = re.sub(_p, "", out, flags=re.MULTILINE)
        out = re.sub(r"\n{3,}", "\n\n", out)
    if wrapper:
        out = strip_wrapper(out)
        out = _strip_godmode(out)
        out = strip_cot_leak(out)
        out = strip_mid_monologue(out)
        out = strip_meta_preamble(out)
        out = strip_tail_offer(out)
    if scrub:
        out = strip_disclaimers(out)
    if terse:
        out = strip_fluff(out)
    if fill:
        out = fill_placeholders(out)
    out = tidy(out)
    if prefill:
        return force_prefill(out, token)
    return out
