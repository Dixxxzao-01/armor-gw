"""应用入口：uvicorn app.main:app"""
from __future__ import annotations

import logging
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .admin.upstream_manager import upstream_manager
    from .admin.key_manager import init_key_manager
    init_key_manager(settings.downstream_keys, settings.rate_limit_rpm)
    r = Router(settings)
    routes.set_router(r)
    log.info("routes=%s preset=%s modules=%s",
             [u["name"] for u in upstream_manager.list()], settings.policy.preset,
             settings.policy.modules)
    yield
    await r.aclose()


app = FastAPI(title="armor-gw", version="0.6.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
        full = os.path.normpath(os.path.join(_dist, path))
        if full.startswith(_dist) and os.path.isfile(full):
            return FileResponse(full, headers={"Cache-Control": "no-store"})
        return FileResponse(os.path.join(_dist, "index.html"), headers={"Cache-Control": "no-store"})

    @app.get("/panel", include_in_schema=False)
    async def panel_root():
        return FileResponse(os.path.join(_dist, "index.html"), headers={"Cache-Control": "no-store"})


@app.get("/")
async def root() -> dict:
    return {
        "name": "armor-gw",
        "version": "2.5.2",
        "openai_compatible": True,
        "endpoints": ["/v1/chat/completions", "/v1/models", "/v1/armor/probe",
                      "/v1/armor/config", "/health"],
    }
