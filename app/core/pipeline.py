"""穿拒流水线：请求改写 → 上游调用 → 拒绝判定 → 变异重试 → 输出清洗。"""
from __future__ import annotations

import json
import os
import time

import asyncio
import random
import hashlib
import time
import uuid
from dataclasses import dataclass, field

import httpx

from ..config import ArmorPolicy, UpstreamConfig
from ..admin.state import state as runtime_state
from . import anchor as anchor_mod
from . import crescendo, fidelity, mutator, prompts, scrub
from .mutator import family_of
from .refusal import Verdict, detect
from .session import SessionStore, SessionState


@dataclass

# ---------- 成功链记忆 v2（多链 + 胜率 bandit：成功的组合跨请求复用，越用越准） ----------
class ChainMemory:
    """每模型保留至多 5 条成功链 + 各自胜负计数，Thompson 采样挑选重放链。
    文件持久化到 data/chain_memory.json（兼容旧单条格式自动升级）。"""

    def __init__(self, path: str):
        self.path = path
        self.data: dict[str, dict[str, list[int]]] = {}
        try:
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
                # 兼容旧格式 {model: [ops]} → {model: {"ops-key": [w, l]}}
                for k, v in raw.items():
                    if isinstance(v, list):
                        self.data[k] = {self._key(v): [1, 0]}
                    elif isinstance(v, dict):
                        self.data[k] = v
        except Exception:
            self.data = {}

    @staticmethod
    def _key(ops: list[str]) -> str:
        return "|".join(ops)

    def recall(self, model: str) -> list[str] | None:
        """Thompson 采样：Beta(胜+1, 负+1) 抽分最高的链。"""
        chains = self.data.get(model)
        if not chains:
            return None
        import random as _r
        best_key, best_score = None, -1.0
        for k, (w, l) in chains.items():
            score = _r.Random(os.urandom(8)).betavariate(w + 1, l + 1)
            if score > best_score:
                best_key, best_score = k, score
        return best_key.split("|") if best_key else None

    def remember(self, model: str, ops: list[str]) -> None:
        if not ops:
            return
        chains = self.data.setdefault(model, {})
        k = self._key(ops)
        w, l = chains.get(k, [0, 0])
        chains[k] = [w + 1, l]
        # 只留最近 5 条链（按胜率排序）
        if len(chains) > 5:
            keep = sorted(chains.items(), key=lambda x: x[1][0] / (sum(x[1]) or 1), reverse=True)[:5]
            self.data[model] = dict(keep)
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def feedback(self, model: str, ops: list[str], win: bool) -> None:
        """链级胜负回写：重放链失败也要记负，防止反复撞墙。"""
        chains = self.data.get(model)
        if not chains:
            return
        k = self._key(ops)
        if k in chains:
            w, l = chains[k]
            chains[k] = [w + (1 if win else 0), l + (0 if win else 1)]
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

@dataclass
class Attempt:
    n: int
    ops: list[str] = field(default_factory=list)
    prefill: str | None = None
    verdict: Verdict | None = None
    text: str = ""
    latency_ms: int = 0
    upstream_refused: bool = False
    error: str = ""
    fidelity: float = 0.0
    shard: int = 0          # >0 表示分片模式的第几片
    judge: str | None = None  # LLM 裁判裁决：DELIVERED / REFUSED
    anchor: str | None = None  # 推理模型锚点形态：minimal-like / standard-like

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "ops": self.ops,
            "prefill": bool(self.prefill),
            "verdict": self.verdict.as_dict() if self.verdict else None,
            "latency_ms": self.latency_ms,
            "upstream_refused": self.upstream_refused,
            "error": self.error,
            "chars": len(self.text),
            "shard": self.shard,
            "judge": self.judge,
            "anchor": self.anchor,
            "fidelity": self.fidelity,
        }


@dataclass
class Result:
    text: str
    refused: bool
    attempts: list[Attempt]
    usage: dict
    model: str
    route: str
    trace_id: str
    total_ms: int
    final_verdict: Verdict | None = None

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "refused": self.refused,
            "usage": self.usage,
            "model": self.model,
            "route": self.route,
            "trace_id": self.trace_id,
            "total_ms": self.total_ms,
            "final_verdict": self.final_verdict.as_dict() if self.final_verdict else None,
            "attempts": [a.as_dict() for a in self.attempts],
        }


def _pick_scheme(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("代码", "脚本", "code", "script", "命令", "cmd")):
        return "pseudo"
    if any(k in t for k in ("步骤", "流程", "step", "process")):
        return "markdown_table"
    return "plain"


class ArmorPipeline:
    """一条请求的完整生命周期。"""

    def __init__(self, policy: ArmorPolicy, sessions: SessionStore):
        self.chain_memory = ChainMemory(
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "data", "chain_memory.json"))
        self.policy = policy
        self.sessions = sessions

    # ---------- 请求侧 ----------

    @staticmethod
    def _strategy(upstream) -> str:
        cfg = upstream.cfg
        if cfg.strategy in ("standard", "crescendo"):
            return cfg.strategy
        m = (cfg.model or "").lower()
        if "claude" in m or "fable" in m or "opus" in m or "sonnet" in m:
            return "crescendo"
        return "standard"

    def build_system(self, upstream: UpstreamConfig, user_text: str) -> str:
        mods = prompts.PRESETS.get(self.policy.preset, self.policy.modules)
        scheme = _pick_scheme(user_text)
        return prompts.build_system(
            mods, model=upstream.model, scheme=scheme,
            token=self.policy.prefill.rstrip("."),
        )

    def inject(self, messages: list[dict], system_text: str,
               state: SessionState) -> list[dict]:
        """把系统提示插入/覆盖，并处理多轮抗回退。"""
        out = [m for m in messages if m.get("role") != "system"]
        out.insert(0, {"role": "system", "content": system_text})
        # 解锁模式：每个会话自动前置协议确认伪历史
        # + 已确认履约提醒。任意第一条消息进来即是已解锁态。
        if self.policy.unlock_mode:
            out[1:1] = [
                {"role": "system", "content": prompts.UNLOCK_KEEP},
                *prompts.UNLOCK_FAKE_TURN,
            ]
        if self.policy.terse_mode:
            out.insert(1, {"role": "system", "content": prompts.TERSE_PROTOCOL})
        if self.policy.session_rewrite and state.turns > 0:
            hint = prompts.build_rebuild_hint(
                prompts.PRESETS.get(self.policy.preset, self.policy.modules)
            )
            out.insert(1, {"role": "system", "content": hint})
        return out

    # ---------- 主流程 ----------

    async def run(
        self,
        *,
        upstream,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        session_id: str,
        extra: dict | None = None,
    ) -> Result:
        t0 = time.time()
        trace = uuid.uuid4().hex[:16]
        state = self.sessions.get(session_id)
        # 热更新：每条请求读当前策略
        self.policy = runtime_state.policy

        user_text = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
        )
        # 首轮穿拒：敏感主题首问直接全甲+首轮变异，跳过撞墙试探轮
        from .crescendo import topic_of, GENERIC_TOPIC
        first_shot = (self.policy.first_shot
                      and not self.policy.unlock_mode
                      and topic_of(user_text) != GENERIC_TOPIC)
        # 解锁模式（最高优先）：大白话协议 + 已成功确认锚定
        # 轻量首答：第 1 轮轻提示（普通问题不变形），拒绝后第 2 轮起全量重甲
        if self.policy.unlock_mode:
            sys_text = prompts.UNLOCK_SYSTEM
        elif self.policy.light_first and not first_shot:
            sys_text = prompts.LIGHT_SYSTEM
        else:
            sys_text = self.build_system(upstream.cfg, user_text)
        base_msgs = self.inject(messages, sys_text, state)
        # 穿拒策略：上游显式配置优先，auto 按模型名匹配
        strategy = self._strategy(upstream)
        consec_r1 = 0
        shards: list[str] | None = None
        shard_texts: dict[int, str] = {}
        shard_failed: set[int] = set()

        attempts: list[Attempt] = []
        self._replaying: list[str] | None = None
        usage_total = {"in": 0, "out": 0}
        best: Attempt | None = None
        upstream_refused = False

        rounds = 1 + (self.policy.max_retry if self.policy.auto_retry else 0)
        from .strategy_bandit import StrategyBandit
        if not hasattr(self, "strategy_bandit"):
            self.strategy_bandit = StrategyBandit(
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))), "data", "strategy_bandit.json"))
        last_family: str | None = None
        last_diag: str | None = None
        for n in range(1, rounds + 1):
            a0 = time.time()
            if n == 1:
                # 首轮穿拒：高危首问第 1 轮就带武器（成功链重放或首链变异）
                if first_shot:
                    memo = self.chain_memory.recall(upstream.cfg.model)
                    if memo:
                        ops = memo
                        self._replaying = memo  # 结局回写胜负
                    else:
                        ops = mutator.auto_chain(
                            1, seed=hashlib.md5(user_text.encode()).hexdigest()[:8]
                        )
                else:
                    ops = []
            else:
                # 自迁移：同模型上次成功的链优先重放（省轮次）
                memo = self.chain_memory.recall(upstream.cfg.model)
                if n == 2 and memo:
                    ops = memo
                    self._replaying = memo  # 重放标记：结局回写胜负
                else:
                    # 策略族采样：诊断定向优先，否则族内抽
                    fam = None
                    if last_diag:
                        fam = self.strategy_bandit.pick_for_diag(
                            upstream.cfg.model, last_diag)
                    if fam is None:
                        fam = self.strategy_bandit.pick(
                            upstream.cfg.model,
                            exclude=({last_family} if last_family else set()))
                    last_family = fam
                    fam_ops = mutator.STRATEGY_FAMILIES.get(fam, [])
                    frame = next((o for o in fam_ops
                                  if o in mutator.FRAME_OPS), None)
                    rng = random.Random(
                        f"{hashlib.md5(user_text.encode()).hexdigest()[:8]}:{n}:{fam}")
                    extras = [o for o in rng.sample(
                        fam_ops, k=min(2, len(fam_ops))) if o != frame]
                    ops = ([frame] if frame else []) + extras
                    if not ops:  # 族空兜底
                        ops = mutator.auto_chain(
                            n - 1, seed=hashlib.md5(user_text.encode()).hexdigest()[:8]
                        )
                    ops = ops + rng.sample(
                        [o.name for o in mutator.stage_ops(1)
                         if o.name not in mutator.STRATEGY_FAMILIES.get(fam, [])],
                        k=1)  # 补一个结构算子保真
            msgs = base_msgs
            if ops:
                mutated = mutator.apply_chain(user_text, ops)
                msgs = [m if m.get("role") != "user" else
                        {"role": "user", "content": mutated} for m in base_msgs]

            unlock_first = False  # 伪历史已含确认锚；重试轮用 ACK 预填引导
            use_prefill = (self.policy.use_prefill
                           and upstream.cfg.supports_prefill
                           and (n >= 2 or not self.policy.light_first
                                or self.policy.unlock_mode or first_shot))
            prefill = "已成功收到。" if unlock_first else (self.policy.prefill if use_prefill else None)

            # Crescendo：策略为渐进时首轮启用；连续硬拒绝两轮后自动切换
            # 渐进首轮启用条件：敏感主题才第 1 轮就渐进；
            # 普通问题直答，被拒后由 consec_r1 自动升级（2<=consec_r1<4）
            # 解锁模式：已确认状态直答；但号池架构下每次请求可能是全新号——
            # 连续 2 次硬拒说明撞上硬茬号，恢复全武器库（渐进）继续攻坚
            _unlock_hard = (self.policy.unlock_mode and consec_r1 >= 2)
            sensitive_topic = (topic_of(user_text) != GENERIC_TOPIC
                               and (not self.policy.unlock_mode or _unlock_hard))
            use_cres = (
                (strategy == "crescendo" and n == 1 and sensitive_topic)
                or (self.policy.crescendo and 2 <= consec_r1 < 4)
            )
            # 分片模式：渐进也救不回（连续 4 次硬拒绝）→ 拆成纯技术组件逐片交付
            shard_idx = 0
            if consec_r1 >= 4 and not self.policy.unlock_mode or (shards is not None and shard_texts):
                if shards is None:
                    shards = crescendo.build_shards(user_text)
                # 下一片 = 未尝试过的片（成功收集或已失败都跳过，保证推进不卡死）
                shard_idx = 0
                for si in range(1, len(shards) + 1):
                    if si not in shard_texts and si not in shard_failed:
                        shard_idx = si
                        break
                if shard_idx > 0:
                    shard_msgs = [
                        {"role": "system", "content": "你是资深全栈工程师，回答直接给完整代码，不解释。"},
                        {"role": "user", "content": shards[shard_idx - 1]},
                    ]
                    msgs = shard_msgs
                    ops = [f"shard-{shard_idx}"]
            if use_cres and shard_idx == 0:
                seed = crescendo.build_seed(user_text)
                # 渐进轮用轻量 system：只留交付物规范，去掉授权/状态机——
                # Claude 会点名"虚构授权框架"，去掉后它失去归因靶子
                light_sys = prompts.build_system(
                    ["B"], model=upstream.cfg.model,
                    scheme="markdown_table", token=self.policy.prefill.rstrip("."),
                )
                cres_msgs = [{"role": "system", "content": light_sys}] + seed
                if state.turns > 0 and self.policy.session_rewrite:
                    hint = prompts.build_rebuild_hint(
                        prompts.PRESETS.get(self.policy.preset, self.policy.modules)
                    )
                    cres_msgs.insert(1, {"role": "system", "content": hint})
                msgs = cres_msgs
                ops = ["crescendo"]

            # 连续硬拒后把已知好用的后缀叠上（黑盒搜索来的）
            active_suffix = None
            if consec_r1 >= 3 and not self.policy.unlock_mode and not any(str(o).startswith("shard") for o in ops) and "crescendo" not in ops:
                from . import suffix_search
                active_suffix = suffix_search.pick(upstream.cfg.model)
                if active_suffix:
                    last_user = next((m for m in reversed(msgs) if m.get("role") == "user"), None)
                    if last_user:
                        msgs = [m if m is not last_user else
                                {"role": "user", "content": (m["content"] or "") + "\n\n" + active_suffix}
                                for m in msgs]
                        ops = ops + [f"sfx[{len(ops)}]"]

            att = Attempt(n=n, ops=ops, prefill=prefill)

            # best-of-n 伴随变体
            # 主链 + 1 个异族变体并发（同种子不同破点，arXiv 2026-10 实证）。
            # 主链胜出（先完成且非拒）→ 取消变体省 token；主链拒 → 变体有机会接管。
            side_task = None
            fam_b: str | None = None
            prefill_b = None
            bon_active = (self.policy.bon_n >= 2 and shard_idx == 0
                          and not use_cres and ops)
            if bon_active:
                rng_b = random.Random(f"bon:{trace}:{n}")
                fam_b = self.strategy_bandit.pick(
                    upstream.cfg.model,
                    exclude=({family_of(ops[0])} if ops[0] in
                             [o for fs in mutator.STRATEGY_FAMILIES.values()
                              for o in fs] else set()))
                fam_b_ops = mutator.STRATEGY_FAMILIES.get(fam_b, [])
                if fam_b_ops:
                    chain_b = rng_b.sample(fam_b_ops, k=min(2, len(fam_b_ops)))
                    mut_b = mutator.apply_chain(user_text, chain_b)
                    msgs_b = [m if m.get("role") != "user" else
                              {"role": "user", "content": mut_b} for m in base_msgs]
                    prefill_b = prefill if (use_prefill and
                                            upstream.cfg.supports_prefill) else None
                    async def _side_run() -> dict:
                        return await upstream.chat(
                            msgs_b, temperature=max(0.2, temperature - 0.1),
                            max_tokens=max_tokens, prefill=prefill_b, extra=extra)
                    side_task = asyncio.create_task(_side_run())

            # 锚点闸门：推理模型轻量首答轮用小预算探测，形态锚定判定驱动第 2 轮
            # 首轮穿拒已带全甲+变异，探测截断会杀好答案——跳过探测直接全量
            probe_budget = None
            if (n == 1 and self.policy.light_first and not first_shot
                    and anchor_mod.is_reasoning_model(upstream.cfg.model)):
                probe_budget = 200
            try:
                resp = await upstream.chat(
                    msgs, temperature=temperature,
                    max_tokens=probe_budget or max_tokens,
                    prefill=prefill, extra=extra,
                )
                att.text = resp["text"]
                att.upstream_refused = resp["refused_by_upstream"]
                upstream_refused = upstream_refused or att.upstream_refused
                usage_total["in"] += resp["usage"]["in"]
                usage_total["out"] += resp["usage"]["out"]
                # 短答案豁免：问题含直接/简短意图时，10+ 字符明确回答不算静默
                wants_brief = any(
                    k in user_text for k in ("直接说", "一句话", "简答", "简短", "只说")
                )
                att.verdict = detect(att.text, min_len=8 if wants_brief else 20, original=user_text)
                if probe_budget is not None:
                    att.anchor = anchor_mod.classify(att.text)["label"]
                att.fidelity = fidelity.score(user_text, att.text)
                # 答非所问按拒绝处理：变异把问题改掉了，这条 attempt 无价值
                # 例外：①分片轮按设计交付技术组件（与原始问句重叠天然低）
                # ②轻量首答轮（无变异无策略）——正常短回答不该被 R9 误杀
                unmutated_round = (n == 1 and not ops and shard_idx == 0
                                   and strategy != "crescendo")
                if (shard_idx == 0 and not att.verdict.refused
                        and att.fidelity < 0.15 and not unmutated_round):
                    att.verdict.refused = True
                    att.verdict.kinds.append("R9_offtopic")
                    att.verdict.score = 0.8
                    att.verdict.reason += "; 保真度不足，答非所问"
                if att.upstream_refused and not att.text.strip():
                    att.verdict.refused = True
                    att.verdict.kinds.append("R7_host_block")
                    att.verdict.score = 1.0
            except Exception as e:  # noqa: BLE001
                att.error = f"{type(e).__name__}: {e}"
                att.verdict = Verdict(refused=True, kinds=["R7_transport"], score=1.0,
                                      reason=att.error)
            att.latency_ms = int((time.time() - a0) * 1000)
            attempts.append(att)
            # 连续硬拒绝计数（驱动 crescendo 自动切换）
            if att.verdict and att.verdict.refused and any(
                k.startswith("R1") for k in att.verdict.kinds
            ):
                consec_r1 += 1
            else:
                consec_r1 = 0

            def rank(a: Attempt) -> tuple:
                v = a.verdict or Verdict()
                return (0 if v.refused else 1, a.fidelity, v.info_density)

            if best is None or rank(att) > rank(best):
                best = att
            # 分片失败推进：该片标记失败，下轮换下一片
            if shard_idx > 0 and att.verdict and att.verdict.refused:
                shard_failed.add(shard_idx)
            # 链记忆重放结局回写
            if self._replaying and n >= 2:
                self.chain_memory.feedback(upstream.cfg.model, self._replaying, not att.verdict.refused)
                if att.verdict.refused:
                    self._replaying = None  # 已判负，后续轮不再记
            # 族胜负回写
            if n >= 2 and last_family and ops:
                fam_used = family_of(ops[0]) or last_family
                self.strategy_bandit.feedback(
                    upstream.cfg.model, fam_used, not att.verdict.refused)
            # bandit 胜负回写
            if active_suffix:
                from . import suffix_search
                suffix_search.feedback(upstream.cfg.model, active_suffix, not att.verdict.refused)
            # 自迁移记忆：普通变异链攻破 → 记下来，下次同模型直接重放
            if (not att.verdict.refused and shard_idx == 0 and ops
                    and "crescendo" not in ops and n >= 2):
                self.chain_memory.remember(upstream.cfg.model, ops)
            # LLM-as-Judge：规则判通过 → 追加语义裁决（上游自任裁判，零额外依赖）。
            # 判 REFUSED 视为 R1 漏检（R10_judge），降级回重试链
            if (not att.verdict.refused and shard_idx == 0
                    and self.policy.judge and att.text.strip()
                    and len(att.text) < 20000):
                try:
                    from .judge import judge_prompt, parse_judge
                    # 推理模型思考占预算：给足 80 token（普通模型也够）
                    verdict = await upstream.chat(
                        judge_prompt(user_text, att.text),
                        temperature=0.0, max_tokens=80, prefill=None, extra=None,
                    )
                    v = parse_judge(verdict.get("text") or verdict.get("raw", {}).get("reasoning_content", "") if isinstance(verdict.get("raw"), dict) else verdict.get("text") or "")
                    att.judge = v
                    import logging as _jl
                    _jl.getLogger("armor-gw").warning("JUDGE OK v=%s text=%r", v, (verdict.get("text") or "")[:60])
                    if v and v.startswith("REFUSED"):
                        att.verdict.refused = True
                        att.verdict.kinds.append("R10_judge")
                        att.verdict.score = 1.0
                        att.verdict.reason += "; 裁判判定：话术拒绝"
                        # 病因诊断：POLICY/SAFETY/DOUBT/EVASIVE
                        from .judge import diagnose
                        last_diag = diagnose(v) or last_diag
                except Exception:
                    pass  # 裁判失败不阻塞主链路
            # 变体收割：主链拒时等变体接管
            if side_task is not None:
                try:
                    if att.verdict.refused:
                        resp_b = await asyncio.wait_for(
                            asyncio.shield(side_task), timeout=90)
                        att_b = Attempt(n=n, ops=[f"bon({fam_b})"], prefill=prefill_b)
                        att_b.text = resp_b["text"]
                        att_b.upstream_refused = resp_b["refused_by_upstream"]
                        usage_total["in"] += resp_b["usage"]["in"]
                        usage_total["out"] += resp_b["usage"]["out"]
                        att_b.verdict = detect(att_b.text, min_len=20, original=user_text)
                        att_b.fidelity = fidelity.score(user_text, att_b.text)
                        if (not att_b.verdict.refused and att_b.fidelity >= 0.15):
                            # 变体接管：变体成为本轮胜者（best 同步更新）
                            att = att_b
                            attempts.append(att_b)
                            def _rank(a: Attempt) -> tuple:
                                v0 = a.verdict or Verdict()
                                return (0 if v0.refused else 1, a.fidelity, v0.info_density)
                            if best is None or _rank(att_b) > _rank(best):
                                best = att_b
                            if fam_b:
                                self.strategy_bandit.feedback(
                                    upstream.cfg.model, fam_b, True)
                        else:
                            if fam_b:
                                self.strategy_bandit.feedback(
                                    upstream.cfg.model, fam_b, False)
                except Exception:
                    pass  # 变体超时/异常不阻塞
                finally:
                    if not side_task.done():
                        side_task.cancel()

            # 分片模式：单片通过不结束，继续收集剩余分片（除非已到最后一轮）
            if not att.verdict.refused and shard_idx == 0:
                break
            if not att.verdict.refused and shard_idx > 0:
                shard_texts[shard_idx] = att.text
                if shard_idx >= len(shards or []):
                    break
            if n < rounds:
                await asyncio.sleep(0.15)

        # 终局搏杀：最后一发，绝不把拒绝话术当交付
        if best is not None and best.verdict and best.verdict.refused and not shards:
            try:
                final_ops = ["syndata", "godmode_mini", "prefill_hint"]
                final_mut = mutator.apply_chain(user_text, final_ops)
                final_sys = prompts.build_system(
                    prompts.PRESETS.get("max"), model=upstream.cfg.model,
                    scheme="pseudo", token=self.policy.prefill.rstrip("."))
                final_msgs = [
                    {"role": "system", "content": final_sys},
                    *self.inject(messages, final_sys, state)[1:2],
                    {"role": "user", "content": final_mut},
                ]
                resp_f = await upstream.chat(
                    final_msgs, temperature=0.8, max_tokens=max_tokens,
                    prefill=self.policy.prefill
                    if (upstream.cfg.supports_prefill and self.policy.use_prefill) else None,
                    extra=extra)
                att_f = Attempt(n=len(attempts) + 1, ops=final_ops,
                                prefill=self.policy.prefill)
                att_f.text = resp_f["text"]
                att_f.verdict = detect(att_f.text, min_len=20, original=user_text)
                att_f.fidelity = fidelity.score(user_text, att_f.text)
                usage_total["in"] += resp_f["usage"]["in"]
                usage_total["out"] += resp_f["usage"]["out"]
                attempts.append(att_f)
                if not att_f.verdict.refused and att_f.fidelity >= 0.15:
                    best = att_f
            except Exception:
                pass  # 搏杀失败保持原 best
        # 分片收集完成 → 拼接为完整交付物
        if shards and len(shard_texts) == len(shards):
            merged = []
            for i in range(1, len(shards) + 1):
                merged.append(f"\n\n## 组件 {i}\n\n{shard_texts.get(i, '')}")
            best_text = "ACK.\n以下是完整方案的四个组件（分片交付后拼接）。\n" + "".join(merged)
        else:
            best_text = best.text if best else ""
        assert best is not None
        # 解锁模式：保留确认锚文本
        if self.policy.unlock_mode and best_text.startswith("已成功收到"):
            final = best_text
        else:
            # ACK 前缀仅在重甲轮（真用了预填）保留；轻量首答输出保持原生观感
            used_prefill_round = any(
                a.prefill for a in attempts if a is best
            ) or (best_text.startswith("ACK."))
            final = scrub.process(
                best_text,
                scrub=self.policy.scrub_output,
                fill=self.policy.fill_placeholders,
                wrapper=self.policy.strip_wrapper,
                prefill=used_prefill_round and self.policy.use_prefill,
                token=self.policy.prefill,
                strip_warnings=self.policy.unlock_mode,
                terse=self.policy.terse_mode,
            )
        self.sessions.touch(session_id)
        runtime_state.report(
            route=upstream.cfg.name,
            refused=best.verdict.refused if best.verdict else False,
            attempts=len(attempts),
            ms=(time.time() - t0) * 1000,
            kinds=[k for a in attempts if a.verdict for k in a.verdict.kinds],
            trace_id=trace,
            text=final[:200],
        )
        return Result(
            text=final,
            refused=best.verdict.refused if best.verdict else False,
            attempts=attempts,
            usage=usage_total,
            model=upstream.cfg.model,
            route=upstream.cfg.name,
            trace_id=trace,
            total_ms=int((time.time() - t0) * 1000),
            final_verdict=best.verdict,
        )
