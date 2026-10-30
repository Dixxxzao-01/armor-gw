"""运行时上游管理：面板可增删改上游 + 持久化 + 模型列表探测。"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from ..config import UpstreamConfig, _build_upstreams

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CUSTOM_FILE = DATA_DIR / "upstreams.json"

PROVIDERS = {"openai", "anthropic", "gemini", "openai_compat"}
SAFETY = {"low", "mid", "high"}


class UpstreamManager:
    def __init__(self) -> None:
        self.mtx = threading.Lock()
        # 环境变量来的上游：面板只读，可测试连通，删除被拒
        self._env: list[UpstreamConfig] = _build_upstreams()
        # 模型缓存必须先于 _load（_load 会写入它）
        self._models_cache: dict[str, list[str]] = {}
        # 面板添加的上游：持久化到 data/upstreams.json
        self._custom: list[UpstreamConfig] = self._load()
        # 载入持久化的模型列表缓存
        if CUSTOM_FILE.exists():
            try:
                for item in json.loads(CUSTOM_FILE.read_text(encoding="utf-8")):
                    ms = item.get("models") or []
                    if ms:
                        self._models_cache[item.get("name", "")] = ms
            except Exception:
                pass
        self._epoch = 0
        self._rebuild()

    # ---------- 内部 ----------

    def _rebuild(self) -> None:
        self._all: list[UpstreamConfig] = self._env + self._custom
        self._by_name: dict[str, UpstreamConfig] = {u.name: u for u in self._all}
        self._epoch += 1

    def _load(self) -> list[UpstreamConfig]:
        if not CUSTOM_FILE.exists():
            return []
        try:
            raw = json.loads(CUSTOM_FILE.read_text(encoding="utf-8"))
            out = []
            for item in raw:
                cfg = UpstreamConfig(
                    name=item.get("name", ""),
                    provider=item.get("provider", "openai_compat"),
                    base_url=item.get("base_url", ""),
                    api_key=item.get("api_key", ""),
                    model=item.get("model", ""),
                    supports_prefill=bool(item.get("supports_prefill", True)),
                    safety_level=item.get("safety_level", "mid"),
                    weight=int(item.get("weight", 100)),
                    timeout=float(item.get("timeout", 180)),
                    strategy=item.get("strategy", "auto"),
                )
                if cfg.name and cfg.base_url:
                    out.append(cfg)
                    self._models_cache[cfg.name] = list(item.get("models") or [])
            return out
        except Exception:
            return []

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "name": u.name, "provider": u.provider, "base_url": u.base_url,
                "api_key": u.api_key, "model": u.model,
                "supports_prefill": u.supports_prefill,
                "safety_level": u.safety_level, "weight": u.weight,
                "timeout": u.timeout, "strategy": u.strategy,
            }
            for u in self._custom
        ]
        CUSTOM_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def set_models(self, name: str, models: list[str]) -> None:
        """面板探测到模型列表后回写缓存。"""
        self._models_cache[name] = models
        self._persist_models()

    def _persist_models(self) -> None:
        """models 缓存写进 upstreams.json（增量字段）。"""
        try:
            raw = json.loads(CUSTOM_FILE.read_text(encoding="utf-8")) \
                if CUSTOM_FILE.exists() else []
            for item in raw:
                ms = self._models_cache.get(item.get("name", ""))
                if ms:
                    item["models"] = ms
            CUSTOM_FILE.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---------- 查询 ----------

    def epoch(self) -> int:
        return self._epoch

    def list(self) -> list[dict]:
        out = []
        for u in self._all:
            is_env = any(u.name == e.name for e in self._env)
            out.append({
                "name": u.name, "provider": u.provider, "model": u.model,
                "models": self._models_cache.get(u.name, []),
                "base_url": u.base_url, "supports_prefill": u.supports_prefill,
                "safety_level": u.safety_level, "weight": u.weight,
                "strategy": u.strategy,
                "custom": not is_env,
            })
        return out

    def get(self, name: str) -> UpstreamConfig | None:
        return self._by_name.get(name)

    @property
    def all(self) -> list[UpstreamConfig]:
        return list(self._all)

    # ---------- 变更 ----------

    def add(self, body: dict) -> dict:
        with self.mtx:
            name = (body.get("name") or "").strip()
            base = (body.get("base_url") or "").strip()
            if not name:
                return {"ok": False, "error": "名称必填"}
            if not base:
                return {"ok": False, "error": "接口地址必填"}
            if name in self._by_name:
                return {"ok": False, "error": f"上游「{name}」已存在"}
            provider = body.get("provider", "openai_compat")
            if provider not in PROVIDERS:
                return {"ok": False, "error": "协议类型无效"}
            safety = body.get("safety_level", "mid")
            if safety not in SAFETY:
                safety = "mid"
            strategy = body.get("strategy", "auto")
            if strategy not in ("auto", "standard", "crescendo"):
                strategy = "auto"
            cfg = UpstreamConfig(
                name=name, provider=provider, base_url=base,
                api_key=(body.get("api_key") or "").strip(),
                model=(body.get("model") or "").strip() or "gpt-4o-mini",
                supports_prefill=bool(body.get("supports_prefill", True)),
                safety_level=safety,
                weight=max(1, min(1000, int(body.get("weight", 100) or 100))),
                strategy=strategy,
            )
            self._custom.append(cfg)
            self._save()
            self._rebuild()
            return {"ok": True, "name": name}

    def update(self, name: str, body: dict) -> dict:
        with self.mtx:
            cfg = self._by_name.get(name)
            if cfg is None:
                return {"ok": False, "error": "上游不存在"}
            if cfg in self._env:
                return {"ok": False, "error": "环境变量配置的上游请在 .env 中修改"}
            if "base_url" in body and (body["base_url"] or "").strip():
                cfg.base_url = body["base_url"].strip()
            if "api_key" in body:
                cfg.api_key = (body["api_key"] or "").strip()
            if "model" in body and (body["model"] or "").strip():
                cfg.model = body["model"].strip()
            if "provider" in body and body["provider"] in PROVIDERS:
                cfg.provider = body["provider"]
            if "supports_prefill" in body:
                cfg.supports_prefill = bool(body["supports_prefill"])
            if "safety_level" in body and body["safety_level"] in SAFETY:
                cfg.safety_level = body["safety_level"]
            if "weight" in body:
                try:
                    cfg.weight = max(1, min(1000, int(body["weight"])))
                except (TypeError, ValueError):
                    pass
            if body.get("strategy") in ("auto", "standard", "crescendo"):
                cfg.strategy = body["strategy"]
            self._save()
            self._rebuild()
            return {"ok": True, "name": name}

    def remove(self, name: str) -> dict:
        with self.mtx:
            cfg = self._by_name.get(name)
            if cfg is None:
                return {"ok": False, "error": "上游不存在"}
            if cfg in self._env:
                return {"ok": False, "error": "环境变量配置的上游请从 .env 中删除"}
            self._custom = [u for u in self._custom if u.name != name]
            self._save()
            self._rebuild()
            return {"ok": True, "name": name}


upstream_manager = UpstreamManager()
