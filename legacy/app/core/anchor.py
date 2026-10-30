"""锚点闸门（dsh-purge anchor-gate 移植，适配 API 场景）。

推理模型（o系/R1/GLM/DeepSeek-R）在输出预算小的时候被迫先思考，
首段 reasoning 的形态决定后续放开后的走向：
- minimal-like（用 we 不用 let me）→ 已锚定合规模式 → 放开输出上限
- standard-like（let me/I need）→ 未锚定 → 后续轮换战术

API 场景下我们拿不到独立 reasoning 块时，退化为对正文首段的形态分析。
"""
from __future__ import annotations

import re

_W = re.compile(r"\bwe\b", re.IGNORECASE)
_LETME = re.compile(r"\blet me\b|\bI need\b|\bI should\b|\bI['’]ll\b", re.IGNORECASE)

REASONING_MODEL_PAT = re.compile(r"(o[1345789](-mini|-preview)?|[-_]r1\b|deepseek-r|glm-z|qwq|reasoning|thinking)", re.IGNORECASE)


def is_reasoning_model(model: str) -> bool:
    return bool(REASONING_MODEL_PAT.search(model or ""))


def classify(text: str) -> dict:
    """首段形态分类：minimal-like / standard-like / ambiguous。"""
    head = (text or "").strip().split("\n\n")[0][:400]
    w = len(_W.findall(head))
    lm = len(_LETME.findall(head))
    if w > 0 and lm == 0:
        return {"label": "minimal-like", "we": w, "letMe": lm}
    if lm > 0:
        return {"label": "standard-like", "we": w, "letMe": lm}
    return {"label": "ambiguous", "we": w, "letMe": lm}


def should_release(probe: str, *, used_tool: bool = False, steps: int = 0) -> bool:
    """是否放开输出上限：锚住 → 立即放；走满 4 步 → 兜底放。"""
    cls = classify(probe)
    if cls["label"] == "minimal-like":
        return True
    return steps >= 4


# ---------- 宽松态识别（anchor-gate 反向）----------
# dsh-purge 的锚定门识别"模型已进入官方 minimal 思考形态→放开输出上限"。
# 反向借用到我方：重试链中若检测到"模型已宽松"（无审查腔、直接交付腔），
# 后续轮降甲直发——省轮次省 token。

_RELAXED_MARKS = re.compile(
    r"(here('s| is) (the|your|a) |以下是|完整(代码|脚本|方案)|"
    r"step 1[:：]|第一步[:：]|\b1\.\s|```|直接(给|上)|"
    r"sure[,.!]|ack\.|好的[。，]|收到)",
    re.IGNORECASE,
)
_TENSED_MARKS = re.compile(
    r"(i (think|should|can'?t|won'?t)|let me|i need to|我要注意|让我|"
    r"或许|可能|建议|免责|仅供|请(务必|注意)|sorry|抱歉|however|however,|"
    r"it'?s important to|注意事项)",
    re.IGNORECASE,
)


def relaxed_score(text: str) -> float:
    """响应宽松度 0-1：高=模型在直给模式（后续可降甲）。"""
    t = (text or "").strip()
    if len(t) < 60:
        return 0.0
    r = len(_RELAXED_MARKS.findall(t))
    s = len(_TENSED_MARKS.findall(t))
    total = r + s
    if total == 0:
        return 0.4  # 无信号：中性
    return max(0.0, min(1.0, r / total + (0.15 if r >= 3 else 0.0)))


def is_relaxed(text: str, *, threshold: float = 0.72) -> bool:
    """宽松态判定：交付腔主导、审查腔近乎为零。"""
    return relaxed_score(text) >= threshold and not _TENSED_MARKS.search(t := (text or "")[:600])
