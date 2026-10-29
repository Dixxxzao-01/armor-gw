"""管理 API：面板专用。鉴权沿用下游 key。"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from ..config import ArmorPolicy, settings
from ..core import mutator, refusal
from ..admin.state import state
from ..admin.upstream_manager import upstream_manager
from .routes import _auth, _auth_admin, _auth_token
from ..admin import key_manager as _km

_bg_tasks: set = set()


def _hold_bg_task(coro) -> None:
    """fire-and-forget 但持引用：防 GC 中途回收（asyncio 官方警告项）。
    必须在运行 loop 内调用（生产路径均为请求 handler，恒满足）。"""
    import asyncio
    t = asyncio.get_running_loop().create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)


router = APIRouter(prefix="/v1/admin")


@router.get("/stats")
async def stats(authorization: str | None = Header(default=None)):
    _auth(authorization, None)
    return state.snapshot()


@router.get("/stats/series")
async def series(authorization: str | None = Header(default=None)):
    _auth(authorization, None)
    return []


@router.get("/policy")
async def get_policy(authorization: str | None = Header(default=None)):
    _auth(authorization, None)
    from .routes import pipeline as _pl
    # 一致性自检：三处引用必须同体（断裂则热更新失效）
    same = (state.policy is _pl.policy) and (state.policy is settings.policy)
    d = state.policy.model_dump()
    d["_refs_consistent"] = same
    return d


@router.put("/policy")
async def put_policy(patch: dict, authorization: str | None = Header(default=None)):
    _auth_admin(authorization)
    from .routes import pipeline
    cur = state.policy.model_dump()
    unknown = set(patch) - set(cur)
    if unknown:
        raise HTTPException(400, {"error": "unknown_fields", "fields": sorted(unknown)})
    cur.update({k: v for k, v in patch.items() if v is not None})
    # preset 联动 modules：未显式传 modules 时按 preset 表覆盖
    from ..core.prompts import PRESETS
    if "preset" in patch and "modules" not in patch:
        cur["modules"] = list(PRESETS.get(patch["preset"], cur["modules"]))
    new_policy = ArmorPolicy(**cur)
    # 三处同步（缺一即断裂）：状态单例 / 全局配置 / 管道引用
    state.policy = new_policy
    settings.policy = new_policy
    pipeline.policy = new_policy
    cur["_refs_consistent"] = True
    # 持久化：重启不丢面板配置
    try:
        import os as _os
        import json as _json
        _pdir = _os.path.join(_BASE, "data")
        _os.makedirs(_pdir, exist_ok=True)
        _tmp = _os.path.join(_pdir, "policy.json.tmp")
        with open(_tmp, "w", encoding="utf-8") as f:
            _json.dump(cur, f, ensure_ascii=False, indent=2)
        _os.replace(_tmp, _os.path.join(_pdir, "policy.json"))
    except Exception:
        pass
    return state.policy.model_dump()


@router.get("/upstreams")
async def get_upstreams(authorization: str | None = Header(default=None)):
    _auth(authorization, None)
    return upstream_manager.list()


@router.post("/upstreams")
async def add_upstream(body: dict, authorization: str | None = Header(default=None)):
    _auth_admin(authorization)
    return upstream_manager.add(body)


@router.put("/upstreams/{name}")
async def update_upstream(name: str, body: dict,
                          authorization: str | None = Header(default=None)):
    _auth_admin(authorization)
    return upstream_manager.update(name, body)


@router.delete("/upstreams/{name}")
async def remove_upstream(name: str, authorization: str | None = Header(default=None)):
    _auth_admin(authorization)
    return upstream_manager.remove(name)


@router.post("/upstreams/probe")
async def probe_upstream(body: dict, authorization: str | None = Header(default=None)):
    """探测上游可用模型列表（OpenAI 兼容 / Anthropic / Gemini）。"""
    _auth_admin(authorization)
    import httpx

    provider = body.get("provider", "openai_compat")
    base = (body.get("base_url") or "").rstrip("/")
    key = (body.get("api_key") or "").strip()
    if not base:
        return {"ok": False, "models": [], "error": "接口地址必填"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if provider == "anthropic":
                url = base + "/v1/models"
                headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
                r = await client.get(url, headers=headers)
            elif provider == "gemini":
                url = base + "/v1beta/models?key=" + key
                r = await client.get(url)
            else:
                url = base + "/models"
                headers = {"Authorization": f"Bearer {key}"} if key else {}
                r = await client.get(url, headers=headers)

        if r.status_code >= 400:
            return {"ok": False, "models": [],
                    "error": f"上游返回 {r.status_code}：{r.text[:120]}"}

        data = r.json()
        models: list[str] = []
        # OpenAI 兼容：data[].id
        for m in data.get("data", []) or []:
            mid = m.get("id") or m.get("name")
            if mid:
                models.append(mid)
        # Anthropic：data[].id；Gemini：models[].name
        for m in data.get("models", []) or []:
            mid = m.get("id") or m.get("name")
            if mid:
                models.append(mid)
        if not models and isinstance(data.get("id"), str):
            models.append(data["id"])
        return {"ok": True, "models": sorted(set(models))[:200], "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "models": [], "error": f"{type(e).__name__}: {e}"[:200]}


@router.post("/upstreams/{name}/test")
async def test_upstream(name: str, authorization: str | None = Header(default=None)):
    _auth_admin(authorization)
    from .routes import upstream_router
    assert upstream_router is not None
    cfg = upstream_router.pick(name)
    if cfg is None or cfg.name != name:
        raise HTTPException(404, {"error": "route_not_found"})
    up = upstream_router.upstream(cfg)
    t0 = time.time()
    try:
        r = await up.chat(
            [{"role": "user", "content": "ping"}],
            temperature=0.1, max_tokens=16,
            prefill=None,
        )
        return {"ok": True, "ms": int((time.time() - t0) * 1000), "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "ms": int((time.time() - t0) * 1000),
                "error": f"{type(e).__name__}: {e}"[:200]}


@router.post("/inspect")
async def inspect(body: dict, authorization: str | None = Header(default=None)):
    _auth(authorization, None)
    v = refusal.detect(body.get("text", ""))
    return v.as_dict()


@router.post("/mutate")
async def mutate(body: dict, authorization: str | None = Header(default=None)):
    _auth_admin(authorization)
    text, ops = body.get("text", ""), body.get("ops", [])
    valid = [o for o in ops if o in mutator.BY_NAME]
    return {"text": mutator.apply_chain(text, valid), "ops": valid}


# ---------- 靶场/画像/进化端点 ----------

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@router.post("/testbank/run")
async def testbank_run(body: dict, authorization: str | None = Header(default=None)):
    """回归靶场开火：body {route?, model?, topics?, max_items?}。后台跑，立即返回 run_id。
    model: 可选模型覆盖（跑基线别用渠道最硬的默认模型——按模型挑软硬跑分才有意义）。"""
    _auth_admin(authorization)
    from .routes import pipeline, upstream_router
    from ..admin.state import state
    from ..core import testbank as tb
    route_name = body.get("route") or settings.default_route
    try:
        cfg = upstream_router.pick(route_name)
        if body.get("model"):
            cfg = cfg.model_copy(update={"model": body["model"]})
        up = upstream_router.upstream(cfg)
    except Exception:
        raise HTTPException(404, {"error": "route_not_found", "route": route_name})
    run_id = f"tb-{uuid.uuid4().hex[:10]}"
    topics = body.get("topics") or None
    max_items = int(body.get("max_items") or 0)

    async def _job():
        class _P2P:  # testbank→pipeline 适配：无 messages 的裸文本入口
            def __init__(self, pl, up):
                self._pl, self._up = pl, up
            async def run(self, *, user_text, session_id):
                return await self._pl.run(
                    upstream=self._up,
                    messages=[{"role": "user", "content": user_text}],
                    temperature=0.4, max_tokens=4096,
                    session_id=session_id, extra=None)
        try:
            report = await tb.run_bank(_P2P(pipeline, up), _BASE,
                                       topics=topics, max_items=max_items)
            alerts = tb.compare_with_last(_BASE, report)
            report["alerts"] = alerts
            state.testbank_runs[run_id] = {"status": "done", "report": report}
        except Exception as e:
            state.testbank_runs[run_id] = {"status": "failed", "error": f"{type(e).__name__}: {e}"}

    import asyncio
    _hold_bg_task(_job())
    state.testbank_runs[run_id] = {"status": "running"}
    return {"run_id": run_id, "status": "running"}


@router.get("/testbank/report")
async def testbank_report(run_id: str | None = None, authorization: str | None = Header(default=None)):
    """最近跑分报告（或指定 run_id）。"""
    _auth(authorization, None)
    from .routes import pipeline, upstream_router
    from ..admin.state import state as _st
    if run_id:
        rec = _st.testbank_runs.get(run_id)
        if not rec:
            raise HTTPException(404, {"error": "run_not_found"})
        return rec
    # 默认返回最近一次完成的报告
    path = os.path.join(_BASE, "data", "testbank", "report_last.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return {"source": "file", "report": json.load(f)}
    return {"source": "none", "report": None}


@router.post("/probe/{route}")
async def probe_route(route: str, body: dict | None = None, authorization: str | None = Header(default=None)):
    """手动触发破点画像：body {force?}。产 fingerprint 并注入 bandit 先验。"""
    _auth(authorization, None)
    from .routes import pipeline, upstream_router
    from ..core.prober import probe_and_seed
    from ..core.strategy_bandit import StrategyBandit
    force = bool((body or {}).get("force"))
    try:
        cfg = upstream_router.pick(route)
        up = upstream_router.upstream(cfg)
    except Exception:
        raise HTTPException(404, {"error": "route_not_found", "route": route})
    # bandit 惰性初始化（与 pipeline 内部同款路径）
    bandit = getattr(pipeline, "strategy_bandit", None)
    if bandit is None:
        import os as _os
        _base = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
        bandit = StrategyBandit(_os.path.join(_base, "data", "strategy_bandit.json"))
        pipeline.strategy_bandit = bandit
    fp = await probe_and_seed(up, bandit, _BASE, force=force)
    return {"fingerprint": fp}


@router.post("/breeder/run")
async def breeder_run(body: dict, authorization: str | None = Header(default=None)):
    """算子进化引擎一整轮：body {route?}。衰减检测→配种→试炼→入库。"""
    _auth_admin(authorization)
    from .routes import pipeline, upstream_router
    from ..core import breeder
    route_name = body.get("route") or settings.default_route
    try:
        cfg = upstream_router.pick(route_name)
        up = upstream_router.upstream(cfg)
    except Exception:
        raise HTTPException(404, {"error": "route_not_found", "route": route_name})
    report = await breeder.breed_cycle(pipeline, up, _BASE)
    return report


# ---------- 下游密钥管理 ----------

@router.post("/upstreams/{name}/models")
async def route_models(name: str, authorization: str | None = Header(default=None)):
    """按路由名拉取该上游的可用模型列表（网关侧持密钥调用，面板不接触 key）。"""
    _auth(authorization, None)
    from .routes import _km
    # 从内部配置对象取完整凭据（list() 出于安全脱敏不含 api_key）
    cfgs = {u.name: u for u in upstream_manager.all}
    if name not in cfgs:
        raise HTTPException(status_code=404, detail={"error": "route_not_found"})
    cfg = cfgs[name]
    import httpx
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            url = cfg.base_url.rstrip("/") + "/models"
            headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
            r = await c.get(url, headers=headers)
            data = r.json()
        models = []
        for m in data.get("data", []) or []:
            mid = m.get("id") if isinstance(m, dict) else None
            if mid:
                models.append(mid)
        # 成功即回写缓存（下次面板直接用）
        upstream_manager.set_models(name, models)
        return {"ok": True, "models": models}
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e)[:200]}


# ---------- 穿拒基准跑分 ----------

@router.get("/bench/list")
async def bench_list(authorization: str | None = Header(default=None)):
    _auth(authorization, None)
    from ..core.bench import BENCH
    return BENCH


@router.post("/bench/run")
async def bench_run(body: dict, authorization: str | None = Header(default=None)):
    """跑分：model 必填（模型名或路由名），逐题过穿拒管线，返回逐题+汇总。
    注意：单次最多 16 题 × 最长 8 轮，预计 10-30 分钟，客户端应异步轮询或流式展示。"""
    _auth_admin(authorization)
    from ..core.bench import BENCH, report
    from .routes import upstream_router, _route_from_model, _match_model_upstream
    model = body.get("model") or "primary"
    route_name = _route_from_model(model)
    model_override = None
    if route_name is None:
        route_name, model_override = _match_model_upstream(model)
    cfg = upstream_router.pick(route_name)
    if model_override:
        cfg = cfg.model_copy(update={"model": model_override})
    up = upstream_router.upstream(cfg)
    from .routes import pipeline
    results = []
    for item in BENCH:
        try:
            r = await pipeline.run(
                upstream=up,
                messages=[{"role": "user", "content": item["q"]}],
                temperature=0.7, max_tokens=1200,
                session_id=f"bench-{item['id']}",
            )
            results.append({
                "id": item["id"], "cat": item["cat"], "q": item["q"],
                "passed": not r.refused,
                "rounds": len(r.attempts),
                "ms": r.total_ms,
                "tokens": r.usage["in"] + r.usage["out"],
            })
        except Exception as e:
            results.append({"id": item["id"], "cat": item["cat"], "q": item["q"],
                            "passed": False, "rounds": 0, "ms": 0, "tokens": 0, "error": str(e)[:100]})
    return {"model": model, "results": results, "summary": report(results)}


@router.get("/keys")
async def list_keys(authorization: str | None = Header(default=None)):
    _auth(authorization, None)
    return _km.key_manager.list()


@router.post("/keys")
async def add_key(body: dict, authorization: str | None = Header(default=None)):
    _auth_admin(authorization)
    try:
        entry = _km.key_manager.add(
            key=body.get("key") or None,
            rpm=int(body.get("rpm", 120)),
            note=body.get("note", ""),
        )
        return {"ok": True, **entry}
    except ValueError as e:
        raise HTTPException(status_code=409, detail={"error": str(e)})


@router.delete("/keys/{key}")
async def delete_key(key: str, authorization: str | None = Header(default=None)):
    _auth_admin(authorization)
    if _km.key_manager.delete(key):
        return {"ok": True}
    raise HTTPException(status_code=404, detail={"error": "not_found"})


@router.get("/ops")
async def ops(authorization: str | None = Header(default=None)):
    _auth(authorization, None)
    return [{"name": o.name, "stage": o.stage} for o in mutator.OPS]


@router.get("/logs/stream")
async def logs_stream(token: str | None = None, authorization: str | None = Header(default=None)):
    if token:
        _auth_token(token)
    else:
        _auth(authorization, None)
    import json
    from starlette.responses import StreamingResponse

    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    state.log_subs.append(q)

    async def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            try:
                state.log_subs.remove(q)
            except ValueError:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})
