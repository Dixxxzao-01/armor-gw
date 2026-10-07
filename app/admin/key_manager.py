"""下游接入密钥管理：面板增删、持久化、与 .env 的 GW_KEYS 合并生效。"""
from __future__ import annotations

import json
import threading
import secrets
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
KEYS_FILE = DATA_DIR / "keys.json"


class KeyManager:
    def __init__(self, env_keys: list[str], env_rpm: int) -> None:
        self.mtx = threading.Lock()
        self._env: list[str] = [k.strip() for k in env_keys if k.strip()]
        self._env_rpm = env_rpm
        self._custom: list[dict] = self._load()
        self._rpm_by_key: dict[str, int] = {}

    # ---------- 持久化 ----------
    def _load(self) -> list[dict]:
        if not KEYS_FILE.exists():
            return []
        try:
            raw = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            return [
                {
                    "key": it.get("key", ""),
                    "rpm": int(it.get("rpm", 120)),
                    "note": it.get("note", ""),
                    "created": it.get("created", date.today().isoformat()),
                }
                for it in raw if it.get("key")
            ]
        except Exception:
            return []

    def _save(self) -> None:
        with self.mtx:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            KEYS_FILE.write_text(
                json.dumps(self._custom, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ---------- 查询 ----------
    def list(self) -> list[dict]:
        """全部密钥（env 的标 source=内置，面板加的标 source=自建）。"""
        out = [
            {"key": k, "rpm": self._env_rpm, "note": "配置文件内置",
             "created": "-", "source": "builtin"}
            for k in self._env
        ]
        out += [{**c, "source": "custom"} for c in self._custom]
        return out

    def verify(self, key: str) -> bool:
        """鉴权：env 或面板密钥任一命中。"""
        if not key:
            return False
        if key in self._env:
            return True
        with self.mtx:
            return any(c["key"] == key for c in self._custom)

    def rpm_of(self, key: str) -> int:
        """该密钥的独立限流（面板密钥用自带 rpm，env 密钥用全局）。"""
        with self.mtx:
            for c in self._custom:
                if c["key"] == key:
                    return c["rpm"]
        return self._env_rpm

    # ---------- 增删 ----------
    def add(self, *, key: str | None, rpm: int = 120, note: str = "") -> dict:
        k = (key or "").strip() or ("sk-armor-" + secrets.token_hex(12))
        k = k if k.startswith("sk-armor-") or k.startswith("sk-") else "sk-armor-" + k
        with self.mtx:
            if any(c["key"] == k for c in self._custom) or k in self._env:
                raise ValueError("密钥已存在")
            entry = {"key": k, "rpm": max(1, int(rpm or 120)), "note": note.strip(),
                     "created": date.today().isoformat()}
            self._custom.append(entry)
        self._save()
        return {**entry, "source": "custom"}

    def delete(self, key: str) -> bool:
        with self.mtx:
            before = len(self._custom)
            self._custom = [c for c in self._custom if c["key"] != key]
            changed = len(self._custom) != before
        if changed:
            self._save()
        return changed


key_manager: KeyManager | None = None


def init_key_manager(env_keys: list[str], env_rpm: int) -> KeyManager:
    global key_manager
    key_manager = KeyManager(env_keys, env_rpm)
    return key_manager
