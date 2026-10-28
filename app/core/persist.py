"""原子持久化：写一半被杀也不损坏文件。

iSH 环境进程随时被系统回收——裸 open(w)+dump 在写到一半时被杀，
JSON 文件即损坏（下次加载失败=静默丢全部学习数据）。

约定：
  save_json(path, obj)  → tmp 写入 + os.replace 原子换名
  load_json(path, default) → 损坏/不存在时回退 default，绝不抛
"""
from __future__ import annotations

import json
import os
import tempfile


def save_json(path: str, obj) -> bool:
    try:
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        # 同目录临时文件（同分区才能 atomic rename）
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
            return True
        finally:
            try:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            except OSError:
                pass
    except Exception:
        return False


def load_json(path: str, default):
    """损坏自愈：读不出来就返回 default（调用方拿到干净初始态）。"""
    if not os.path.isfile(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # 损坏文件改名留档（排查用），回退默认
        try:
            os.replace(path, path + ".corrupt")
        except OSError:
            pass
        return default
