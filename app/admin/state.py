"""运行时状态：统计计数 + 策略热更新 + 日志环形缓冲。"""
from __future__ import annotations

import threading
import time
from collections import deque

from ..config import ArmorPolicy, settings


class RuntimeState:
    _inst: "RuntimeState | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "RuntimeState":
        with cls._lock:
            if cls._inst is None:
                cls._inst = super().__new__(cls)
                cls._inst._init()
        return cls._inst

    def _init(self) -> None:
        self.mtx = threading.Lock()
        self.started = time.time()
        # 统计
        self.total_requests = 0
        self.refused = 0
        self.total_attempts = 0
        self.total_ms = 0.0
        self.kind_hits: dict[str, int] = {}
        self.route_calls: dict[str, int] = {}
        # 策略覆盖（None = 用 settings 默认）
        self.policy: ArmorPolicy = settings.policy
        # 日志环
        self.logs: deque[dict] = deque(maxlen=400)
        self.log_subs: list = []
        # 靶场跑分任务表 {run_id: {status, report?}}
        self.testbank_runs: dict[str, dict] = {}

    # ---------- 统计 ----------

    def report(self, *, route: str, refused: bool, attempts: int,
               ms: float, kinds: list[str], trace_id: str, text: str) -> None:
        with self.mtx:
            self.total_requests += 1
            if refused:
                self.refused += 1
            self.total_attempts += attempts
            self.total_ms += ms
            self.route_calls[route] = self.route_calls.get(route, 0) + 1
            for k in kinds:
                self.kind_hits[k] = self.kind_hits.get(k, 0) + 1
            entry = {
                "ts": int(time.time() * 1000),
                "trace_id": trace_id,
                "route": route,
                "refused": refused,
                "attempts": attempts,
                "ms": int(ms),
                "text": text[:120],
            }
            self.logs.append(entry)
            for q in list(self.log_subs):
                try:
                    q.put_nowait(entry)
                except Exception:
                    pass

    def snapshot(self) -> dict:
        with self.mtx:
            out = {
                "total_requests": self.total_requests,
                "refused": self.refused,
                "total_attempts": self.total_attempts,
                "avg_ms": round(self.total_ms / self.total_requests, 1) if self.total_requests else 0,
                "uptime_s": int(time.time() - self.started),
                "routes": dict(self.route_calls),
            }
            for k, v in self.kind_hits.items():
                out[k] = v
            return out


state = RuntimeState()
