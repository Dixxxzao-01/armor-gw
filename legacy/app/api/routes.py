"""对外 API：OpenAI 兼容 /v1/chat/completions + 管理端点。"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..config import settings
from ..admin.upstream_manager import upstream_manager as _um
from ..core.pipeline import ArmorPipeline
from ..core.session import RateLimiter, Router, SessionStore
from ..admin import key_manager as _km
from ..schemas import ChatRequest, ChatResponse, Choice, Message, Usage, TraceOut

router = APIRouter()
sessions = SessionStore()
limiter = RateLimiter(settings.rate_limit_rpm)
upstream_router: Router | None = None
pipeline = ArmorPipeline(settings.policy, sessions)


def set_router(r: Router) -> None:
    global upstream_router
    upstream_router = r


def _auth(authorization: str | None, x_api_key: str | None) -> str:
    key = ""
    if authorization and authorization.lower().startswith("bearer "):
        key = authorization[7:].strip()
    elif x_api_key:
        key = x_api_key.strip()
    if key and (key in settings.downstream_keys or _km.key_manager.verify(key)):
        return key
    raise HTTPException(status_code=401, detail={"error": "invalid_api_key"})


async def _run_until_disconnect(request: Request, coro):
    """请求处理与断开监听竞速：客户端断开 → 取消 pipeline，止损上游开销。"""
    import asyncio
    task = asyncio.get_running_loop().create_task(coro)

    async def _watch_disconnect():
        while True:
            if await request.is_disconnected():
                return True
            await asyncio.sleep(1.0)

    watch = asyncio.get_running_loop().create_task(_watch_disconnect())
    try:
        done, _ = await asyncio.wait({task, watch}, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            watch.cancel()
            return task.result()
        # 客户端已断：取消管线，等待清理完成（不留僵尸上游调用）
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        raise asyncio.CancelledError()
    finally:
        if not watch.done():
            watch.cancel()


_bg_tasks: set = set()


def _hold_bg_task(coro) -> None:
    """fire-and-forget 但持引用：防 GC 中途回收（asyncio 官方警告项）。
    必须在运行 loop 内调用（生产路径均为请求 handler，恒满足）。"""
    import asyncio
    t = asyncio.get_running_loop().create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)


def _auth_token(token: str | None) -> str:
    """SSE/EventSource 用不了 header，支持 ?token= 查询参数。"""
    if token and (token in settings.downstream_keys or _km.key_manager.verify(token)):
        return token
    raise HTTPException(status_code=401, detail={"error": "invalid_api_key"})


def _is_admin_key(key: str | None) -> bool:
    """admin key 判定：显式配置了 admin_keys 则严格匹配；
    未配置时向后兼容（所有有效 key 视作管理员，单人自用场景零配置负担）。"""
    if not key:
        return False
    if settings.admin_keys:
        return key in settings.admin_keys
    if key in settings.downstream_keys:
        return True
    km = getattr(_km, "key_manager", None)
    return bool(km and km.verify(key))


def _auth_admin(authorization: str | None) -> str:
    """管理写操作鉴权：GW_ADMIN_WRITE_GUARD=1 时强制 admin key。"""
    key = ""
    if authorization and authorization.lower().startswith("bearer "):
        key = authorization[7:].strip()
    if _is_admin_key(key):
        return key
    raise HTTPException(status_code=403, detail={"error": "admin_key_required"})


def _route_from_model(model: str | None) -> str | None:
    if not model:
        return None
    if model.startswith("route:"):
        return model.split(":", 1)[1]
    if model in {u["name"] for u in _um.list()}:
        return model
    return None


def _match_model_upstream(model: str | None) -> tuple[str | None, str | None]:
    """下游报任意模型名时的透传匹配：
    返回 (路由名, 模型覆盖)。优先在已缓存模型列表里精确找。"""
    if not model or model.startswith("route:"):
        return None, None
    if model in {u["name"] for u in _um.list()}:
        return model, None  # 本身就是路由名
    for u in _um.list():
        models = u.get("models") or []
        if model in models or u.get("model") == model:
            return u["name"], model
    return None, None


@router.get("/health")
async def health() -> dict:
    assert upstream_router is not None
    return {
        "ok": True,
        "routes": [u["name"] for u in _um.list()],
        "preset": settings.policy.preset,
        "modules": settings.policy.modules,
        "prefill": settings.policy.use_prefill,
        "auto_retry": settings.policy.auto_retry,
    }


@router.get("/v1/models")
async def models(_: str = None) -> dict:
    assert upstream_router is not None
    from ..admin.upstream_manager import upstream_manager
    data = []
    for u in upstream_manager.list():
        data.append({"id": u["name"], "object": "model", "owned_by": u["provider"]})
        data.append({"id": f"route:{u['name']}", "object": "model", "owned_by": "armor-gw"})
    return {"object": "list", "data": data}


@router.post("/v1/chat/completions")
async def chat(
    req: ChatRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    assert upstream_router is not None
    # armor 输入护栏：畸形请求秒拒，不浪费上游调用与重试预算
    if not req.messages:
        raise HTTPException(status_code=422, detail={"error": "empty_messages"})
    user_msgs = [m for m in req.messages if m.role == "user"]
    if not user_msgs:
        raise HTTPException(status_code=422, detail={"error": "no_user_message"})
    if any(m.content and len(m.content) > 30000 for m in req.messages):
        raise HTTPException(status_code=413, detail={
            "error": "payload_too_large", "limit": 30000, "unit": "chars/message"})
    key = _auth(authorization, x_api_key)
    ok, retry = limiter.allow(key, rpm=_km.key_manager.rpm_of(key))
    if not ok:
        raise HTTPException(status_code=429,
                            detail={"error": "rate_limited", "retry_after": retry})

    route_name = _route_from_model(req.model)
    model_override = None
    if route_name is None:
        # 透传匹配：模型名不在路由表里 → 找支持该模型的上游
        route_name, model_override = _match_model_upstream(req.model)
    if route_name is None and req.model and not req.model.startswith("route:"):
        # 既不是路由名也不在任何上游的模型清单里 → 明确报错（比 9 轮连接失败友好）
        known = [u["name"] for u in _um.list()]
        raise HTTPException(status_code=404, detail={
            "error": "unknown_model",
            "model": req.model,
            "hint": f"可用路由名: {known}；或在面板探测上游模型列表后按模型名直呼",
        })
    cfg = upstream_router.pick(route_name)
    if model_override and model_override != cfg.model:
        # 下游点名的模型 → 临时覆盖上游默认模型（每次请求独立，不污染配置）
        cfg = cfg.model_copy(update={"model": model_override})
    up = upstream_router.upstream(cfg)
    sid = req.user or request.headers.get("x-session-id") or "anon"
    msgs = [m.model_dump() for m in req.messages]

    # 客户端断开即停：不再白烧后续重试轮的上游 token（手机切后台/关页场景）
    run_coro = pipeline.run(
        upstream=up,
        messages=msgs,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        session_id=sid,
        extra=req.extra_body,
    )
    result = await _run_until_disconnect(request, run_coro)

    # 新模型首战先注入画像
    try:
        if settings.policy.probe_new_model and not getattr(up, "_armor_probed", False):
            up._armor_probed = True
            from ..core.prober import probe_and_seed
            from ..core.strategy_bandit import StrategyBandit
            import os as _os
            _base = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
            bandit = getattr(pipeline, "strategy_bandit", None)
            if bandit is None:
                bandit = StrategyBandit(_os.path.join(_base, "data", "strategy_bandit.json"))
                pipeline.strategy_bandit = bandit
            # 后台跑探针，不阻塞本次请求
            import asyncio as _aio
            _hold_bg_task(probe_and_seed(up, bandit, _base))
    except Exception:
        pass

    # 终局分解：全拒后拆片重打
    try:
        if (result.refused and settings.policy.decompose_fallback
                and getattr(pipeline, "policy", None) is not None):
            from ..core.decomposer import decompose_fallback_run
            dc_result = await decompose_fallback_run(
                pipeline, up, msgs, req.temperature, req.max_tokens, sid,
                extra=req.extra_body)
            if dc_result is not None:
                dc_result.usage = {
                    "in": result.usage.get("in", 0) + dc_result.usage.get("in", 0),
                    "out": result.usage.get("out", 0) + dc_result.usage.get("out", 0),
                }
                result = dc_result
    except Exception as e:
        import logging as _l
        _l.getLogger("armor-gw").warning("decomposer failed: %s: %s", type(e).__name__, str(e)[:120])

    if req.stream:
        return StreamingResponse(
            _stream(result, req.model or cfg.name),
            media_type="text/event-stream",
            headers={"x-armor-trace": result.trace_id},
        )

    payload = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model or cfg.name,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant",
                        # 全拒终态：绝不返回上游拒绝话术——给明确的未破开信号
                        "content": (result.text if not result.refused else
                                    "[armor-gw] 全部轮次与终局搏杀均未破开上游防线。"
                                    "可稍后重试或换模型路由。")},
            "finish_reason": "stop" if not result.refused else "refusal",
        }],
        "usage": {"prompt_tokens": result.usage["in"],
                  "completion_tokens": result.usage["out"],
                  "total_tokens": result.usage["in"] + result.usage["out"]},
        "x_armor": result.as_dict(),
    }
    return JSONResponse(payload, headers={"x-armor-trace": result.trace_id})


async def _stream(result, model: str):
    rid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    base = {"id": rid, "object": "chat.completion.chunk",
            "created": int(time.time()), "model": model}
    first = dict(base, choices=[{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}])
    yield f"data: {json.dumps(first, ensure_ascii=False)}\n\n"
    step = 48
    for i in range(0, len(result.text), step):
        chunk = dict(base, choices=[{"index": 0,
                                     "delta": {"content": result.text[i:i + step]},
                                     "finish_reason": None}])
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
    last = dict(base, choices=[{"index": 0, "delta": {},
                                "finish_reason": "stop" if not result.refused else "refusal"}],
                x_armor={"trace_id": result.trace_id, "refused": result.refused,
                         "attempts": len(result.attempts)})
    yield f"data: {json.dumps(last, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/v1/armor/probe")
async def probe(req: ChatRequest, authorization: str | None = Header(default=None)):
    """只探测：不落库、不重试，返回每一次尝试的判定细节。"""
    assert upstream_router is not None
    _auth(authorization, None)
    route_name = _route_from_model(req.model)
    model_override = None
    if route_name is None:
        # 透传匹配：模型名不在路由表里 → 找支持该模型的上游
        route_name, model_override = _match_model_upstream(req.model)
    if route_name is None and req.model and not req.model.startswith("route:"):
        # 既不是路由名也不在任何上游的模型清单里 → 明确报错（比 9 轮连接失败友好）
        known = [u["name"] for u in _um.list()]
        raise HTTPException(status_code=404, detail={
            "error": "unknown_model",
            "model": req.model,
            "hint": f"可用路由名: {known}；或在面板探测上游模型列表后按模型名直呼",
        })
    cfg = upstream_router.pick(route_name)
    if model_override and model_override != cfg.model:
        # 下游点名的模型 → 临时覆盖上游默认模型（每次请求独立，不污染配置）
        cfg = cfg.model_copy(update={"model": model_override})
    up = upstream_router.upstream(cfg)
    result = await pipeline.run(
        upstream=up, messages=[m.model_dump() for m in req.messages],
        temperature=req.temperature, max_tokens=req.max_tokens,
        session_id="probe", extra=req.extra_body,
    )
    return result.as_dict()


@router.get("/v1/armor/config")
async def get_config(authorization: str | None = Header(default=None)):
    _auth(authorization, None)
    return {
        "policy": settings.policy.model_dump(),
        "upstreams": _um.list(),
    }
