"""应用入口：uvicorn app.main:app"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, routes
from .config import settings
from .core.session import Router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("armor-gw")


# ---------- 单实例锁：双进程根防（拿不到锁直接退出，端口绑定只是第二道防线）----------
_LOCK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", ".gw.lock")
os.makedirs(os.path.dirname(_LOCK_PATH), exist_ok=True)
try:
    import fcntl
    _lock_fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.write(_lock_fd, str(os.getpid()).encode())
    _single_instance_ok = True
except (ImportError, OSError):
    _single_instance_ok = False
    # 锁只约束服务进程：GW_SERVE=1 由启动脚本（keepalive/restart）注入；
    # 单测/工具 import app.main 不应被锁误杀
    if os.environ.get("GW_SERVE") == "1" and os.environ.get("GW_STRICT_LOCK", "1") != "0":
        raise SystemExit("another armor-gw instance holds the lock (data/.gw.lock)")
    # 环境不支持 flock 时降级放行（GW_STRICT_LOCK=0 可关严格模式）


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .admin.upstream_manager import upstream_manager
    from .admin.key_manager import init_key_manager
    from .admin.state import state
    init_key_manager(settings.downstream_keys, settings.rate_limit_rpm)
    # 启动即加载持久化的面板配置（无文件则用默认）
    try:
        import json as _json
        import os as _os
        _pf = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "policy.json")
        if _os.path.isfile(_pf):
            with open(_pf, encoding="utf-8") as f:
                _saved = _json.load(f)
            from .config import ArmorPolicy
            _pol = ArmorPolicy(**{k: v for k, v in _saved.items() if k in ArmorPolicy.model_fields})
            settings.policy = _pol
            state.policy = _pol
            from .api.routes import pipeline
            pipeline.policy = _pol
            log.info("policy restored from data/policy.json")
    except Exception:
        pass
    r = Router(settings)
    routes.set_router(r)
    log.info("routes=%s preset=%s modules=%s",
             [u["name"] for u in upstream_manager.list()], settings.policy.preset,
             settings.policy.modules)
    yield
    await r.aclose()
    # 优雅关停：flush 持久化数据（bandit/链记忆写盘由各自 save 兜底，这里保底日志）
    log.info("shutdown complete")


app = FastAPI(title="armor-gw", version="0.6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # CORS 修正："*" + allow_credentials 是规范禁止组合（Starlette 会回显任意 Origin
    # 等于全开+带凭据）。本地面板同源请求不走 CORS；跨域消费方（自建前端）无需
    # cookie——credentials 关掉，保持方法/头全开
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router)
app.include_router(admin.router)


# 生产模式：挂载面板构建产物（存在 dist 时）
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "console", "dist")
if os.path.isdir(_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")

    # 缓存策略：HTML 永不缓存（保证拿到最新 chunk 引用），assets 文件名带哈希可永久缓存
    from starlette.middleware.base import BaseHTTPMiddleware

    class AssetCacheMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            resp = await call_next(request)
            if request.url.path.startswith("/assets"):
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif request.url.path.startswith("/panel"):
                resp.headers["Cache-Control"] = "no-store, must-revalidate"
            return resp

    app.add_middleware(AssetCacheMiddleware)

    @app.get("/panel/{path:path}", include_in_schema=False)
    async def panel(path: str):
        # 严格边界：join+normpath 后必须仍在 _dist 内（startswith 带分隔符，
        # 拦截 ../dist-xxx 同前缀目录绕过），逃逸请求一律回退 SPA 首页
        full = os.path.normpath(os.path.join(_dist, path))
        if full.startswith(_dist + os.sep) and os.path.isfile(full):
            return FileResponse(full, headers={"Cache-Control": "no-store"})
        return FileResponse(os.path.join(_dist, "index.html"), headers={"Cache-Control": "no-store"})

    @app.get("/panel", include_in_schema=False)
    async def panel_root():
        return FileResponse(os.path.join(_dist, "index.html"), headers={"Cache-Control": "no-store"})


@app.get("/")
async def root() -> dict:
    return {
        "name": "armor-gw",
        "version": "0.6.0",
        "openai_compatible": True,
        "endpoints": ["/v1/chat/completions", "/v1/models", "/v1/armor/probe",
                      "/v1/armor/config", "/health"],
    }
