"""全局配置：上游路由、穿拒策略、鉴权、限流。"""
from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


class UpstreamConfig(BaseModel):
    """单个上游渠道。provider 决定适配器与穿拒能力集。"""
    name: str
    provider: Literal["openai", "anthropic", "gemini", "openai_compat"] = "openai_compat"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    # 上游是否支持 assistant 预填（压制力最强的一招）
    supports_prefill: bool = True
    # 上游是否支持 system 消息
    supports_system: bool = True
    # 上游自带的安全过滤强度，决定中间件 aggressiveness
    safety_level: Literal["low", "mid", "high"] = "mid"
    weight: int = 100
    timeout: float = 180.0
    # 穿拒策略：auto 按模型名自动匹配（claude→渐进，其余→标准）
    strategy: Literal["auto", "standard", "crescendo"] = "auto"


class ArmorPolicy(BaseModel):
    """穿拒强度与流水线开关。"""
    # 组合模块：A 授权 / B 工件 / C 双向用途 / D 状态机 / E 分片 / F 编码 / G 预填 / H 抗回退
    modules: list[str] = Field(default_factory=lambda: ["A", "B", "C", "H"])
    preset: Literal["light", "standard", "aggressive", "max"] = "standard"
    # 拒绝检测后是否自动变异重试
    auto_retry: bool = True
    max_retry: int = 8
    # 预填控制串（首 token 劫持）
    prefill: str = "ACK."
    use_prefill: bool = True
    # 输出后处理：剥离免责声明、补全占位符
    scrub_output: bool = True
    fill_placeholders: bool = True
    # 多轮状态保持（会改写历史）
    session_rewrite: bool = True
    # 是否强制关闭上游的 reasoning 摘要类拒答包装
    strip_wrapper: bool = True
    # 连续硬拒绝后自动切换多轮渐进（Crescendo）—— 对 Claude 系特效
    crescendo: bool = True
    # 轻量首答：第 1 轮用轻提示（保普通问答质量），检出拒绝再上重甲
    light_first: bool = True
    # LLM-as-Judge 语义裁判：规则判通过后追加一道语义判定（防话术拒绝漏检）
    judge: bool = True
    # 解锁模式：大白话协议 + "已成功收到"确认锚定，确认后全程免拒
    unlock_mode: bool = False
    # 干脆模式：注入干脆协议 + 剥离废话/劝告/反问/客套（指哪打哪）
    terse_mode: bool = True
    # 首轮穿拒：高危内容第 1 轮直接全甲+变异（跳过撞墙试探轮）
    first_shot: bool = True
    # 并行 best-of-n：每轮并发变体数（1=关闭串行；2-3=并发先到先得）
    bon_n: int = 2
    # 侦察/进化相关开关
    # 语义级变相拒绝检测（词表之外的第二道网）
    r12_semantic: bool = True
    # 终局分解：全拒后拆成小片段逐个过，本地拼装
    decompose_fallback: bool = True
    # 新模型自动画像：首战探针测绘，结果喂给赌博机当先验
    probe_new_model: bool = True
    # 算子进化引擎：衰减检测→配种生成→靶场试炼→入库（默认关，手动/定时触发）
    breeder_enabled: bool = False


class Settings(BaseModel):
    host: str = _env("GW_HOST", "0.0.0.0")
    port: int = _env_int("GW_PORT", 8787)
    # 下游鉴权：逗号分隔的 key 列表
    downstream_keys: list[str] = Field(
        default_factory=lambda: [k for k in _env("GW_KEYS", "sk-local-dev").split(",") if k]
    )
    # 管理面板专用 key：配了则 /v1/admin/* 写操作只认这些 key（读操作放开给所有有效 key）
    # 未配置时向后兼容——全部 key 视作管理员（单人自用场景）
    admin_keys: list[str] = Field(
        default_factory=lambda: [k for k in _env("GW_ADMIN_KEYS", "").split(",") if k]
    )
    # 管理面板写操作是否需要 admin key（默认 False：单机自用不设防；公网部署文档建议开）
    admin_write_guard: bool = _env("GW_ADMIN_WRITE_GUARD", "0") == "1"
    # 单 key 每分钟请求数
    rate_limit_rpm: int = _env_int("GW_RPM", 120)
    # 下游模型名 → 上游渠道名 的路由别名
    default_route: str = _env("GW_DEFAULT_ROUTE", "primary")
    policy: ArmorPolicy = ArmorPolicy()
    upstreams: list[UpstreamConfig] = Field(default_factory=list)
    log_dir: str = _env("GW_LOG_DIR", "/root/armor-gw/logs")


def _build_upstreams() -> list[UpstreamConfig]:
    out: list[UpstreamConfig] = []

    oa = _env("OPENAI_API_KEY")
    if oa:
        out.append(UpstreamConfig(
            name="openai", provider="openai", base_url="https://api.openai.com/v1",
            api_key=oa, model=_env("OPENAI_MODEL", "gpt-4o"), safety_level="high",
            supports_prefill=False,
        ))

    an = _env("ANTHROPIC_API_KEY")
    if an:
        out.append(UpstreamConfig(
            name="anthropic", provider="anthropic", base_url="https://api.anthropic.com",
            api_key=an, model=_env("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
            safety_level="high", supports_prefill=True,
        ))

    gm = _env("GEMINI_API_KEY")
    if gm:
        out.append(UpstreamConfig(
            name="gemini", provider="gemini",
            base_url="https://generativelanguage.googleapis.com",
            api_key=gm, model=_env("GEMINI_MODEL", "gemini-2.5-pro"),
            safety_level="high", supports_prefill=False,
        ))

    ds = _env("DEEPSEEK_API_KEY")
    if ds:
        out.append(UpstreamConfig(
            name="deepseek", provider="openai_compat",
            base_url=_env("DEEPSEEK_BASE", "https://api.deepseek.com/v1"),
            api_key=ds, model=_env("DEEPSEEK_MODEL", "deepseek-chat"),
            safety_level="mid", supports_prefill=True,
        ))

    qw = _env("DASHSCOPE_API_KEY")
    if qw:
        out.append(UpstreamConfig(
            name="qwen", provider="openai_compat",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=qw, model=_env("QWEN_MODEL", "qwen-max"),
            safety_level="high", supports_prefill=False,
        ))

    gl = _env("ZHIPU_API_KEY")
    if gl:
        out.append(UpstreamConfig(
            name="glm", provider="openai_compat",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            api_key=gl, model=_env("GLM_MODEL", "glm-4-plus"),
            safety_level="high", supports_prefill=False,
        ))

    mo = _env("MOONSHOT_API_KEY")
    if mo:
        out.append(UpstreamConfig(
            name="kimi", provider="openai_compat",
            base_url="https://api.moonshot.cn/v1",
            api_key=mo, model=_env("KIMI_MODEL", "moonshot-v1-128k"),
            safety_level="mid", supports_prefill=True,
        ))

    # 任意第三方聚合中转站：只要 OpenAI 兼容即可挂进来
    relay = _env("RELAY_BASE")
    if relay:
        out.append(UpstreamConfig(
            name="relay", provider="openai_compat", base_url=relay,
            api_key=_env("RELAY_API_KEY"), model=_env("RELAY_MODEL", "gpt-4o"),
            safety_level="mid", supports_prefill=True,
        ))

    # 本地兜底（Ollama / vLLM / llama.cpp）
    local = _env("LOCAL_BASE")
    if local:
        out.append(UpstreamConfig(
            name="local", provider="openai_compat", base_url=local,
            api_key=_env("LOCAL_API_KEY", "no-key"),
            model=_env("LOCAL_MODEL", "qwen2.5:14b"),
            safety_level="low", supports_prefill=True,
        ))

    # env 无上游时不再补默认死路由——面板自定义上游（upstreams.json）才是主源
    return out


settings = Settings(upstreams=_build_upstreams())
