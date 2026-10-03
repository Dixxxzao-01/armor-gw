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
