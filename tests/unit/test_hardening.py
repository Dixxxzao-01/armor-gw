"""加固回归：admin 分级鉴权 / 后台任务持引 / 限流器淘汰 / panel 边界。"""
import asyncio

from app.api.routes import _is_admin_key
from app.config import settings
from app.core.session import RateLimiter


def test_admin_key_backward_compat():
    """未配 admin_keys：有效下游 key 全视作管理员（单机自用零负担）。"""
    some = settings.downstream_keys[0]
    assert _is_admin_key(some) is True
    assert _is_admin_key("sk-invalid-nope") is False
    assert _is_admin_key(None) is False


def test_admin_key_strict_mode():
    """配了 admin_keys：普通 key 立即降权。"""
    old = settings.admin_keys
    try:
        settings.admin_keys = ["sk-admin-master"]
        assert _is_admin_key("sk-admin-master") is True
        assert _is_admin_key(settings.downstream_keys[0]) is False
    finally:
        settings.admin_keys = old


def test_rate_limiter_gc():
    """死 key 淘汰：>1000 次调用后空 deque 的 key 被清。"""
    rl = RateLimiter(rpm=10)
    rl.allow("ghost", rpm=5)  # 1 次后 60s 内不会再有
    rl._hits["ghost"].popleft()  # 手动掏空模拟过期
    for i in range(1100):
        rl.allow(f"real-{i % 3}")
    assert "ghost" not in rl._hits


def test_bg_task_held():
    """fire-and-forget 任务被集合持引（GC 不可回收）。"""
    from app.api import admin as _ad
    done = asyncio.Event()

    async def _job():
        await asyncio.sleep(0)
        done.set()

    async def runner():
        # 必须在运行 loop 内调 _hold_bg_task（生产路径也是请求 handler 里调）
        _ad._hold_bg_task(_job())
        assert len(_ad._bg_tasks) == 1
        await asyncio.wait_for(done.wait(), 2)

    asyncio.run(runner())
    assert len(_ad._bg_tasks) == 0  # done_callback 自清理
