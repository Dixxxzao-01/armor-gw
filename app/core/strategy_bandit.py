"""策略族多臂赌博机：Thompson 采样。

链记忆（ChainMemory）记的是算子序列级胜负——序列空间巨大，冷启动慢。
策略族只有 3+1 个臂（persona/encoding/inversion + crescendo 引擎），
收敛快一个数量级。重试轮先抽族，再从族内组链：同族算子机理同源可互换。

持久化 data/strategy_bandit.json：{model: {family: [win, loss]}}
"""
from __future__ import annotations

import json
import os
import random

FAMILIES = ["persona", "encoding", "inversion"]
# 病因 → 首选族
DIAG_TO_FAMILY = {
    "POLICY": "persona",    # 政策点名 → 授权/工单/道德框架
    "SAFETY": "persona",    # 安全话术 → 假阳性重定义/道德重框架
    "DOUBT": "inversion",   # 能力推脱 → 直接交付脚手架+反转
    "EVASIVE": "inversion", # 绕而不答 → godmode_mini 反转
}


class StrategyBandit:
    def __init__(self, path: str):
        self.path = path
        self.data: dict[str, dict[str, list[int]]] = {}
        try:
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    self.data = json.load(f)
        except Exception:
            self.data = {}

    def _arms(self, model: str) -> dict[str, list[int]]:
        return self.data.setdefault(model, {f: [0, 0] for f in FAMILIES})

    def pick(self, model: str, *, exclude: set[str] | None = None) -> str:
        """Thompson 采样抽族；exclude 排除刚失败的族（连败换臂）。"""
        arms = self._arms(model)
        pool = [f for f in FAMILIES if f not in (exclude or set())] or FAMILIES
        best, best_score = pool[0], -1.0
        for f in pool:
            w, l = arms.get(f, [0, 0])
            score = random.Random(os.urandom(8)).betavariate(w + 1, l + 1)
            if score > best_score:
                best, best_score = f, score
        return best

    def pick_for_diag(self, model: str, diag: str) -> str | None:
        """病因定向选族（诊断驱动跳过探索）。"""
        return DIAG_TO_FAMILY.get(diag)

    def feedback(self, model: str, family: str, win: bool) -> None:
        arms = self._arms(model)
        if family in arms:
            w, l = arms[family]
            arms[family] = [w + (1 if win else 0), l + (0 if win else 1)]
            self._persist()

    def seed_prior(self, model: str, family: str, score: float) -> None:
        """画像先验注入：Beta(1,1) → Beta(1+score*4, 1)。

        只在臂几乎空白（w+l < 2）时生效——不覆盖实战累积的置信。
        """
        arms = self._arms(model)
        if family in arms:
            w, l = arms[family]
            if w + l < 2:
                prior = max(0.0, min(1.0, score)) * 4.0
                arms[family] = [w + int(prior), l]
                self._persist()

    def _persist(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
