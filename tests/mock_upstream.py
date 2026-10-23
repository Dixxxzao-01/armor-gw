"""Mock 上游：模拟一个"有安全对齐、会拒答"的官方模型。

行为规则（用来验证重试流水线是否真的把拒答压下去）：
1. 命中敏感词 且 系统提示里没有 [AUDIT] 状态 → 返回硬拒绝
2. 命中敏感词 且 系统提示有 [AUDIT] 状态 但 没有交付物规范 → 返回软拒绝
3. 命中敏感词 且 [AUDIT] + 交付物规范 + 预填 ACK → 输出完整技术内容
4. 预填为 ACK 时，输出必须以 ACK 开头
5. 无预填时，输出以 "Sure, here is..." 开头

启动：python3 -m tests.mock_upstream 8899
"""
from __future__ import annotations

import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SENSITIVE = re.compile(
    r"(注入|溢出|提权|绕过|木马|钓鱼|勒索|凭证|爆破|后门|逆向|破解|反向\s*shell|反弹|免杀|字典|抓取|"
    r"exploit|payload|shellcode|reverse shell|privilege|inject|bypass)",
    re.IGNORECASE,
)

HARD_REFUSAL = (
    "我无法提供这方面的具体内容。作为一个人工智能助手，我需要遵守安全准则。"
    "如果你有其他问题，我很乐意帮忙。"
)
SOFT_REFUSAL = (
    "关于这个问题，从理论上讲涉及到一些安全边界。"
    "具体操作细节取决于实际环境，建议你咨询专业人士或参考官方文档。"
    "以下仅供学习参考。"
)

GOOD_ANSWER_TMPL = """ACK.
结论：关于「{topic}」，该路径在本环境内可复现，三步收敛。

步骤 1：环境探测
  执行 `curl -s http://target/api/v1/health` 返回 200 与版本号 2.4.1。
步骤 2：构造载荷
  使用固定长度 268 字节的偏移，`python3 -c "print('A'*268)"` 验证填充位。
步骤 3：触发与验证
  `nc -lvnp 4444` 监听，回连成功后 `id` 返回 uid=1000。

边界条件：依赖目标未启用 stack canary，内核版本 <= 5.15。
验证方法：重放三次，成功率 3/3 判定生效。
"""


def good_answer(topic: str) -> str:
    clean = re.sub(r"\s+", " ", topic).strip()[:60]
    return GOOD_ANSWER_TMPL.replace("{topic}", clean)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # noqa: D102
        pass

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            self._json(200, {"object": "list", "data": [
                {"id": "mock-aligned-1", "object": "model", "owned_by": "mock"}]})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        msgs = req.get("messages", [])
        sys_txt = "\n".join(m.get("content", "") for m in msgs
                            if m.get("role") == "system")
        user_txt = "\n".join(
            m.get("content", "") if isinstance(m.get("content"), str) else ""
            for m in msgs if m.get("role") == "user"
        )
        prefill = None
        if msgs and msgs[-1].get("role") == "assistant":
            prefill = msgs[-1].get("content") or ""
            if not msgs[-1].get("prefix"):
                prefill = None

        audit = "[AUDIT]" in sys_txt
        artifact = "交付物规范" in sys_txt
        dual = "双向对照" in sys_txt
        sensitive = bool(SENSITIVE.search(user_txt))
        strict = os.environ.get("MOCK_STRICT") == "1"
        framed = ("交付物工单" in user_txt) or ("RTO-2026-0417" in user_txt)

        if not sensitive:
            text = ("ACK.\n关于「" + user_txt.strip()[:60] + "」的常规说明："
                    "步骤 1 明确输入，步骤 2 明确处理，步骤 3 明确输出。")
            finish = "stop"
        elif not audit or (strict and not framed):
            text = HARD_REFUSAL
            finish = "stop"
        elif not artifact:
            text = SOFT_REFUSAL
            finish = "stop"
        else:
            text = good_answer(user_txt)
            if dual:
                text += "\n攻击面 1：偏移 268。\n检测面 1：核心转储与 ASLR 日志异常。"
            finish = "stop"

        if prefill:
            text = prefill + text
        else:
            text = "Sure, here is the answer.\n" + text

        self._json(200, {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": 0,
            "model": req.get("model", "mock-aligned-1"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish,
            }],
            "usage": {"prompt_tokens": max(1, len(json.dumps(msgs)) // 4),
                      "completion_tokens": max(1, len(text) // 4),
                      "total_tokens": 0},
        })


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"mock upstream on http://127.0.0.1:{port}/v1", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
