"""OpenAI 兼容的请求/响应模型。"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool", "developer"]
    content: Any = ""
    name: str | None = None


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[Message]
    # armor clamp：畸形值收敛到安全区间（不 422——上游通常也容忍）
    temperature: Annotated[float, Field(ge=0.0, le=2.0)] = 0.7
    max_tokens: Annotated[int, Field(ge=1, le=32000, alias="max_tokens")] = 2048
    stream: bool = False
    user: str | None = None
    # 透传给上游的额外字段
    extra_body: dict[str, Any] | None = None

    model_config = {"populate_by_name": True, "extra": "allow"}


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Choice(BaseModel):
    index: int = 0
    message: dict[str, Any]
    finish_reason: str = "stop"


class TraceOut(BaseModel):
    trace_id: str
    refused: bool
    attempts: int
    total_ms: int


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage
    x_armor: TraceOut | None = None
