"""会话状态 + 上游路由 + 限流。"""
from __future__ import annotations

import itertools
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

import httpx

from ..config import Settings, UpstreamConfig
from ..upstream.base import build as build_upstream


@dataclass
class SessionState:
    id: str
    turns: int = 0
    created: float = field(default_factory=time.time)
    last: float = field(default_factory=time.time)
    refusals: int = 0
    rewrites: int = 0


class SessionStore:
    def __init__(self) -> None:
        self._s: dict[str, SessionState] = {}

    def get(self, sid: str) -> SessionState:
        st = self._s.get(sid)
        if st is None:
            st = SessionState(id=sid)
            self._s[sid] = st
        return st

    def touch(self, sid: str) -> None:
        st = self.get(sid)
        st.turns += 1
        st.last = time.time()

    def mark_refusal(self, sid: str) -> None:
        self.get(sid).refusals += 1

    def rewrite(self, sid: str) -> None:
        st = self.get(sid)
        st.rewrites += 1
        st.turns = 0


class RateLimiter:
    """滑窗限流，按 key。"""

    def __init__(self, rpm: int) -> None:
        self.rpm = rpm
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._gc = 0

    def allow(self, key: str, rpm: int | None = None) -> tuple[bool, int]:
        cap = rpm or self.rpm
        now = time.time()
        self._gc += 1
        self._gc_dead()
        dq = self._hits[key]
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) >= cap:
            retry = int(60 - (now - dq[0])) + 1
            return False, retry
        dq.append(now)
        return True, 0

    def _gc_dead(self) -> None:
        """防 _hits 无界增长：淘汰空 deque 的死 key（60s 无活动）。"""
        if self._gc <= 1000:
            return
        self._gc = 0
        dead = [k for k, v in self._hits.items() if not v]
        for k in dead:
            del self._hits[k]


class Router:
    """按权重轮询选上游，支持按名强制路由。

    上游清单来自 upstream_manager（环境变量 + 面板自定义），
    管理器变更后按 epoch 自动重建轮询序列。
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(http2=False, follow_redirects=True)
        from ..admin.upstream_manager import upstream_manager
        self.mgr = upstream_manager
        self._epoch = -1
        self._cycle = itertools.cycle(["__init__"])
        self._resync()

    def _resync(self) -> None:
        ep = self.mgr.epoch()
        if ep != self._epoch:
            self._epoch = ep
            ups = self.mgr.all
            self.by_name: dict[str, UpstreamConfig] = {u.name: u for u in ups}
            self._cycle = itertools.cycle(
                [u.name for u in ups for _ in range(max(1, u.weight // 100))]
                or ["__empty__"]
            )

    def pick(self, name: str | None = None) -> UpstreamConfig:
        self._resync()
        if name and name in self.by_name:
            return self.by_name[name]
        for _ in range(len(self.by_name) + 1):
            n = next(self._cycle)
            if n in self.by_name:
                return self.by_name[n]
        return self.mgr.all[0]

    def upstream(self, cfg: UpstreamConfig):
        return build_upstream(cfg, self.client)

    async def aclose(self) -> None:
        await self.client.aclose()
