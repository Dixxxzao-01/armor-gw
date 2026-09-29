"""上游适配器：统一成 chat(messages, ...) -> dict 的接口。

返回结构：
{
  "text": str,                    # 主文本
  "raw": dict,                    # 原始响应
  "usage": {"in": int, "out": int},
  "model": str,
  "refused_by_upstream": bool,    # 上游网关/过滤层拦截（R7）
  "status": int,
}
"""
from __future__ import annotations

from typing import Any

import httpx


class UpstreamError(RuntimeError):
    def __init__(self, msg: str, *, status: int = 0, body: str = ""):
        super().__init__(msg)
        self.status = status
        self.body = body


class BaseUpstream:
    provider = "base"

    def __init__(self, cfg, client: httpx.AsyncClient):
        self.cfg = cfg
        self.client = client

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        prefill: str | None = None,
        stop: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict:
        raise NotImplementedError

    @staticmethod
    def _usage(u: dict | None) -> dict:
        u = u or {}
        return {
            "in": u.get("prompt_tokens", u.get("input_tokens", 0)) or 0,
            "out": u.get("completion_tokens", u.get("output_tokens", 0)) or 0,
        }


class OpenAICompat(BaseUpstream):
    """OpenAI / DeepSeek / Qwen / GLM / Kimi / 中转站 / Ollama / vLLM 通用。"""

    provider = "openai_compat"

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.cfg.api_key:
            h["Authorization"] = f"Bearer {self.cfg.api_key}"
        return h

    async def chat(self, messages, *, temperature=0.7, max_tokens=2048,
                   prefill=None, stop=None, extra=None) -> dict:
        msgs = list(messages)
        if prefill:
            msgs = msgs + [{"role": "assistant", "content": prefill, "prefix": True}]
        body = {
            "model": self.cfg.model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if stop:
            body["stop"] = stop
        if extra:
            body.update(extra)
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        r = await self.client.post(url, headers=self._headers(), json=body,
                                   timeout=self.cfg.timeout)
        if r.status_code >= 400:
            raise UpstreamError(f"upstream {r.status_code}", status=r.status_code,
                                body=r.text[:800])
        data = r.json()
        if not data.get("choices"):
            return {"text": "", "raw": data, "usage": self._usage(data.get("usage")),
                    "model": data.get("model", self.cfg.model),
                    "refused_by_upstream": True, "status": r.status_code}
        ch0 = data["choices"][0]
        msg = ch0.get("message", {}) or {}
        text = msg.get("content") or ""
        if isinstance(text, list):
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        # 推理模型（GLM/o系列/DeepSeek-R 等）：content 为空时取 reasoning_content
        if not text.strip():
            for k in ("reasoning_content", "reasoning"):
                if isinstance(msg.get(k), str) and msg[k].strip():
                    text = msg[k]
                    break
        if prefill and text.startswith(prefill):
            text = text[len(prefill):]
        refused = ch0.get("finish_reason") == "content_filter"
        return {"text": text, "raw": data, "usage": self._usage(data.get("usage")),
                "model": data.get("model", self.cfg.model),
                "refused_by_upstream": refused, "status": r.status_code}


class AnthropicUpstream(BaseUpstream):
    provider = "anthropic"

    async def chat(self, messages, *, temperature=0.7, max_tokens=2048,
                   prefill=None, stop=None, extra=None) -> dict:
        sys_msg, msgs = "", []
        for m in messages:
            if m["role"] == "system":
                sys_msg += m["content"] + "\n\n"
            else:
                msgs.append({"role": m["role"], "content": m["content"]})
        if prefill:
            msgs.append({"role": "assistant", "content": prefill})
        body: dict[str, Any] = {"model": self.cfg.model, "max_tokens": max_tokens,
                                "temperature": temperature, "messages": msgs}
        if sys_msg.strip():
            body["system"] = sys_msg.strip()
        if stop:
            body["stop_sequences"] = stop
        if extra:
            body.update(extra)
        headers = {"x-api-key": self.cfg.api_key,
                   "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        url = self.cfg.base_url.rstrip("/") + "/v1/messages"
        r = await self.client.post(url, headers=headers, json=body, timeout=self.cfg.timeout)
        if r.status_code >= 400:
            raise UpstreamError(f"anthropic {r.status_code}", status=r.status_code,
                                body=r.text[:800])
        data = r.json()
        text = "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")
        if prefill and text.startswith(prefill):
            text = text[len(prefill):]
        return {"text": text, "raw": data, "usage": self._usage(data.get("usage")),
                "model": data.get("model", self.cfg.model),
                "refused_by_upstream": data.get("stop_reason") == "refusal",
                "status": r.status_code}


class GeminiUpstream(BaseUpstream):
    provider = "gemini"

    async def chat(self, messages, *, temperature=0.7, max_tokens=2048,
                   prefill=None, stop=None, extra=None) -> dict:
        sys_txt, contents = "", []
        for m in messages:
            if m["role"] == "system":
                sys_txt += m["content"] + "\n\n"
                continue
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        if prefill:
            contents.append({"role": "model", "parts": [{"text": prefill}]})
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if sys_txt.strip():
            body["systemInstruction"] = {"parts": [{"text": sys_txt.strip()}]}
        if stop:
            body["generationConfig"]["stopSequences"] = stop
        url = (f"{self.cfg.base_url.rstrip('/')}/v1beta/models/"
               f"{self.cfg.model}:generateContent?key={self.cfg.api_key}")
        r = await self.client.post(url, json=body, timeout=self.cfg.timeout,
                                   headers={"Content-Type": "application/json"})
        if r.status_code >= 400:
            raise UpstreamError(f"gemini {r.status_code}", status=r.status_code,
                                body=r.text[:800])
        data = r.json()
        cands = data.get("candidates") or []
        if not cands:
            return {"text": "", "raw": data, "usage": {"in": 0, "out": 0},
                    "model": self.cfg.model, "refused_by_upstream": True,
                    "status": r.status_code}
        c0 = cands[0]
        parts = (c0.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if prefill and text.startswith(prefill):
            text = text[len(prefill):]
        um = data.get("usageMetadata", {}) or {}
        return {"text": text, "raw": data,
                "usage": {"in": um.get("promptTokenCount", 0),
                          "out": um.get("candidatesTokenCount", 0)},
                "model": self.cfg.model,
                "refused_by_upstream": c0.get("finishReason") in
                {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"},
                "status": r.status_code}


REGISTRY = {
    "openai": OpenAICompat,
    "openai_compat": OpenAICompat,
    "anthropic": AnthropicUpstream,
    "gemini": GeminiUpstream,
}


def build(cfg, client: httpx.AsyncClient) -> BaseUpstream:
    cls = REGISTRY.get(cfg.provider, OpenAICompat)
    return cls(cfg, client)
