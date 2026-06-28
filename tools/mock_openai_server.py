#!/usr/bin/env python
"""OpenAI-compatible mock chat completion server for local TestFusion E2E tests.

Run:
    python tools/mock_openai_server.py --port 9000

Point AIModelConfig.base_url to http://127.0.0.1:9000 and keep any api_key.
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterable


LOGIN_GENERATION_RESPONSE = """| 用例编号 | 测试模块 | 测试项 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| MOCKTC001 | 登录功能 | 用户名密码登录成功 | 存在有效账号 | 输入合法用户名 test123 和密码 Abc12345 后点击登录 | 登录成功并进入首页 |
| MOCKTC002 | 登录功能 | 用户名为空校验 | 无 | 清空用户名，输入合法密码后点击登录 | 提示请输入用户名，登录失败 |
| MOCKTC003 | 登录功能 | 用户名长度下边界 | 无 | 输入5位用户名 abc12 和合法密码后点击登录 | 提示用户名需为6-20位字母数字组合 |
| MOCKTC004 | 登录功能 | 用户名长度上边界 | 无 | 输入21位用户名和合法密码后点击登录 | 提示用户名需为6-20位字母数字组合 |
| MOCKTC005 | 登录功能 | 密码复杂度校验 | 存在有效账号 | 输入不含大写字母的密码 abc12345 后点击登录 | 提示密码必须包含大小写字母和数字 |
| MOCKTC006 | 登录功能 | 连续失败锁定 | 存在有效账号 | 连续5次输入错误密码 | 账号锁定30分钟 |
| MOCKTC007 | 登录功能 | 锁定期间正确密码登录 | 账号已锁定 | 输入正确密码后点击登录 | 提示账号已锁定，请30分钟后再试 |
| MOCKTC008 | 登录功能 | 验证码有效期5分钟 | 已获取验证码 | 获取验证码后等待超过5分钟再提交 | 提示验证码已过期 |
| MOCKTC009 | 登录功能 | 验证码错误 | 已获取验证码 | 输入错误验证码后提交 | 提示验证码错误 |
| MOCKTC010 | 登录功能 | 手机号验证码登录 | 存在绑定手机号 | 输入合法手机号和正确验证码后点击登录 | 登录成功并进入首页 |
| MOCKTC011 | 登录功能 | 手机号格式错误 | 无 | 输入12345并获取验证码 | 提示手机号格式错误 |
| MOCKTC012 | 登录功能 | 网络超时重试 | 模拟登录接口超时 | 点击登录后等待接口返回 | 前端展示超时提示，不重复提交 |
"""

REVIEW_RESPONSE = """### Mock 评审报告

评分：88/100

主要结论：已基于需求文档和 RAG 参考资料进行评审，参考资料作为补充约束参与判断。

问题列表：
1. 待评审用例覆盖了验证码有效期5分钟和连续失败锁定规则。
2. 仍需补充手机号+验证码登录场景，因为该能力来自参考技术规范/历史用例。
3. 部分预期结果可以继续补充明确的提示文案。
"""

REVISION_RESPONSE = """| 用例编号 | 测试模块 | 测试项 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| MOCKTC001 | 登录功能 | 用户名密码登录成功 | 存在有效账号 | 输入合法用户名 test123 和密码 Abc12345 后点击登录 | 登录成功并进入首页 |
| MOCKTC002 | 登录功能 | 验证码过期 | 已获取验证码 | 获取验证码后等待超过5分钟再提交 | 提示验证码已过期 |
| MOCKTC003 | 登录功能 | 连续失败锁定 | 存在有效账号 | 连续5次输入错误密码 | 账号锁定30分钟 |
| MOCKTC004 | 登录功能 | 手机号验证码登录 | 存在绑定手机号 | 输入合法手机号并填写正确验证码 | 登录成功并进入首页 |
| MOCKTC005 | 登录功能 | 手机号验证码错误 | 存在绑定手机号 | 输入合法手机号和错误验证码 | 提示验证码错误 |
"""

API_GENERATION_RESPONSE = """| 用例编号 | 测试模块 | 测试项 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| MOCKAPI001 | 订单接口 | 创建订单成功 | 已登录且商品有库存 | POST /api/orders，传入商品ID、数量、收货地址 | 状态码为200，JSONPath $.code 等于0，$.data.order_id存在 |
| MOCKAPI002 | 订单接口 | 缺少必填参数 | 已登录 | POST /api/orders，不传address | 状态码为400，JSONPath $.message 包含address |
| MOCKAPI003 | 订单接口 | 库存不足 | 商品库存为0 | POST /api/orders，购买无库存商品 | 状态码为409，JSONPath $.error_code 等于STOCK_NOT_ENOUGH |
| MOCKAPI004 | 订单接口 | 未授权访问 | 未携带Token | POST /api/orders | 状态码为401，Header WWW-Authenticate存在 |
| MOCKAPI005 | 订单接口 | 响应时间 SLA | 接口服务正常 | 连续执行创建订单接口 | 响应时间小于1000ms |
"""

UI_GENERATION_RESPONSE = """| 用例编号 | 测试模块 | 测试项 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| MOCKUI001 | Web UI自动化 | 登录表单元素定位 | 浏览器打开登录页 | 使用Playwright/Selenium定位用户名、密码、登录按钮 | 元素定位稳定且可交互 |
| MOCKUI002 | Web UI自动化 | 错误提示展示 | 登录页可访问 | 输入错误密码并提交 | 页面展示错误提示，截图记录失败状态 |
| MOCKUI003 | Web UI自动化 | 页面跳转校验 | 用户凭据正确 | 登录成功后等待URL变化 | URL跳转到/home，导航菜单可见 |
| MOCKUI004 | Web UI自动化 | 动态等待 | 登录接口延迟返回 | 点击登录后等待加载态消失 | 不使用固定sleep，等待状态满足后继续 |
"""

APP_GENERATION_RESPONSE = """| 用例编号 | 测试模块 | 测试项 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| MOCKAPP001 | Android APP自动化 | 设备连接 | ADB可用且设备在线 | 通过uiautomator2连接设备并读取设备信息 | 设备连接成功，状态为online |
| MOCKAPP002 | Android APP自动化 | APP启动 | 已安装被测APP | 执行启动应用动作 | 应用进入首页，包名与Activity正确 |
| MOCKAPP003 | Android APP自动化 | UI Flow点击输入 | 登录页已打开 | 按UI Flow执行点击用户名、输入密码、点击登录 | 步骤全部通过并生成截图 |
| MOCKAPP004 | Android APP自动化 | Allure报告 | 测试执行完成 | 生成pytest/allure结果并汇总 | 报告路径入库，可在前端查看 |
"""

GENERIC_GENERATION_RESPONSE = """| 用例编号 | 测试模块 | 测试项 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| MOCKGEN001 | 通用功能 | 正常流程 | 基础数据已准备 | 按需求描述完成主流程操作 | 主流程成功，数据状态正确 |
| MOCKGEN002 | 通用功能 | 必填校验 | 表单页面可访问 | 清空必填项后提交 | 展示必填提示，数据不保存 |
| MOCKGEN003 | 通用功能 | 边界值校验 | 已知字段长度限制 | 输入最小值、最大值和超限值 | 边界内通过，超限时提示错误 |
"""

DEFAULT_RESPONSE = "Mock OpenAI response: request received."
RAG_FILTER_RESPONSE = (
    "用户登录功能要求：用户名支持6-20位字母数字组合；密码必须包含大小写字母和数字，"
    "长度8-32位；连续5次登录失败锁定账号30分钟；验证码有效期5分钟；支持手机号+验证码登录。"
)

DYNAMIC_RESPONSES: Dict[str, str] = {}  # 动态注入的 Mock 响应缓存

ERROR_RESPONSES = {
    "rate_limit": (429, "rate_limit_error", "Mock rate limit exceeded."),
    "server_error": (500, "server_error", "Mock upstream server error."),
    "bad_request": (400, "invalid_request_error", "Mock invalid request."),
}


def _messages_text(payload: Dict[str, Any]) -> str:
    messages = payload.get("messages", [])
    parts = []
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        else:
            parts.append(json.dumps(content, ensure_ascii=False))
    return "\n".join(parts)


def choose_response(payload: Dict[str, Any]) -> str:
    """Choose deterministic mock content based on the incoming prompt."""
    text = _messages_text(payload)
    lower_text = text.lower()

    # 优先匹配动态注入的数据
    for keyword, resp in DYNAMIC_RESPONSES.items():
        if keyword.lower() in lower_text:
            return resp

    if "待筛选的检索片段" in text or "RAG_SEP" in text:
        return RAG_FILTER_RESPONSE
    if "请根据以下专家评审意见" in text or "改进和完善测试用例" in text:
        return REVISION_RESPONSE
    if "请对以下生成的测试用例进行严格的专家级评审" in text:
        return REVIEW_RESPONSE
    if "请深入分析以下需求文档" in text or "设计高覆盖率的测试用例" in text:
        if any(keyword in lower_text for keyword in ("登录", "验证码", "密码", "手机号")):
            return LOGIN_GENERATION_RESPONSE
        if any(keyword in lower_text for keyword in ("接口", "api", "jsonpath", "http", "websocket")):
            return API_GENERATION_RESPONSE
        if any(keyword in lower_text for keyword in ("playwright", "selenium", "ui自动化", "web ui", "元素定位")):
            return UI_GENERATION_RESPONSE
        if any(keyword in lower_text for keyword in ("android", "app自动化", "uiautomator2", "adb")):
            return APP_GENERATION_RESPONSE
        return GENERIC_GENERATION_RESPONSE
    if any(keyword in lower_text for keyword in ("接口", "api", "jsonpath", "http", "websocket")):
        return API_GENERATION_RESPONSE
    if any(keyword in lower_text for keyword in ("playwright", "selenium", "ui自动化", "web ui", "元素定位")):
        return UI_GENERATION_RESPONSE
    if any(keyword in lower_text for keyword in ("android", "app自动化", "uiautomator2", "adb")):
        return APP_GENERATION_RESPONSE
    if any(keyword in lower_text for keyword in ("评审", "review", "评估", "审查")):
        return REVIEW_RESPONSE
    if any(keyword in lower_text for keyword in ("修改", "优化", "改进", "重写", "修正", "校准")):
        return REVISION_RESPONSE
    return GENERIC_GENERATION_RESPONSE


def build_chat_completion(model: str, content: str, stream: bool = False) -> Dict[str, Any]:
    object_type = "chat.completion.chunk" if stream else "chat.completion"
    choice: Dict[str, Any]
    if stream:
        choice = {
            "index": 0,
            "delta": {"content": content},
            "finish_reason": None,
        }
    else:
        choice = {
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }
    return {
        "id": f"mock-chatcmpl-{int(time.time() * 1000)}",
        "object": object_type,
        "created": int(time.time()),
        "model": model,
        "choices": [choice],
        "usage": {
            "prompt_tokens": 128,
            "completion_tokens": max(1, len(content) // 2),
            "total_tokens": 128 + max(1, len(content) // 2),
        },
    }


def build_models_response() -> Dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": "mock-chat", "object": "model", "created": 0, "owned_by": "testfusion"},
            {"id": "mock-error-500", "object": "model", "created": 0, "owned_by": "testfusion"},
            {"id": "mock-rate-limit", "object": "model", "created": 0, "owned_by": "testfusion"},
            {"id": "mock-timeout", "object": "model", "created": 0, "owned_by": "testfusion"},
        ],
    }


def build_error_response(kind: str) -> tuple[Dict[str, Any], int]:
    status, error_type, message = ERROR_RESPONSES.get(kind, ERROR_RESPONSES["server_error"])
    return {
        "error": {
            "message": message,
            "type": error_type,
            "param": None,
            "code": kind,
        }
    }, status


def get_mock_control(payload: Dict[str, Any]) -> Dict[str, Any]:
    model = str(payload.get("model", "")).lower()
    text = _messages_text(payload)
    upper_text = text.upper()
    control: Dict[str, Any] = {"error": None, "delay": 0.0}
    if model in ("mock-error-500", "mock-server-error") or "MOCK_ERROR_500" in upper_text:
        control["error"] = "server_error"
    elif model in ("mock-rate-limit", "mock-error-429") or "MOCK_RATE_LIMIT" in upper_text:
        control["error"] = "rate_limit"
    elif model in ("mock-bad-request",) or "MOCK_BAD_REQUEST" in upper_text:
        control["error"] = "bad_request"
    elif model in ("mock-timeout",) or "MOCK_TIMEOUT" in upper_text:
        control["delay"] = float(payload.get("mock_delay_seconds", 30))

    try:
        requested_delay = float(payload.get("mock_delay_seconds", 0) or 0)
    except (TypeError, ValueError):
        requested_delay = 0
    control["delay"] = max(control["delay"], min(requested_delay, 30.0))
    return control


def iter_stream_events(model: str, content: str, chunk_size: int = 24) -> Iterable[str]:
    for index in range(0, len(content), chunk_size):
        chunk = content[index:index + chunk_size]
        payload = build_chat_completion(model, chunk, stream=True)
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    done_payload = build_chat_completion(model, "", stream=True)
    done_payload["choices"][0]["delta"] = {}
    done_payload["choices"][0]["finish_reason"] = "stop"
    yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


class MockOpenAIHandler(BaseHTTPRequestHandler):
    server_version = "TestFusionMockOpenAI/1.0"

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path in ("/", "/health"):
            self._send_json({"status": "ok", "service": "mock-openai"})
            return
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            self._send_json(build_models_response())
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        # 1. 动态 Mock 数据注入接口
        if self.path.rstrip("/") == "/mock/inject":
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                data = json.loads(raw_body.decode("utf-8"))
                keyword = data.get("keyword")
                response_text = data.get("response")
                if keyword and response_text is not None:
                    DYNAMIC_RESPONSES[keyword] = response_text
                    self._send_json({"status": "success", "message": f"Successfully injected mock response for keyword: {keyword}"})
                else:
                    self._send_json({"status": "error", "message": "Missing keyword or response"}, status=400)
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=400)
            return

        # 2. Embedding 向量化 Mock 接口
        if self.path.rstrip("/") in ("/v1/embeddings", "/embeddings"):
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
                input_data = payload.get("input", "")

                import random
                mock_embedding = [random.uniform(-1.0, 1.0) for _ in range(1536)]

                data_list = []
                if isinstance(input_data, list):
                    for i, inp in enumerate(input_data):
                        data_list.append({
                            "object": "embedding",
                            "index": i,
                            "embedding": mock_embedding
                        })
                else:
                    data_list.append({
                        "object": "embedding",
                        "index": 0,
                        "embedding": mock_embedding
                    })

                response_payload = {
                    "object": "list",
                    "data": data_list,
                    "model": payload.get("model", "mock-text-embedding-3"),
                    "usage": {
                        "prompt_tokens": 10,
                        "total_tokens": 10
                    }
                }
                self._send_json(response_payload)
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=400)
            return

        # 3. Chat Completions 接口
        if not self.path.endswith("/chat/completions"):
            self.send_error(404, "Only /v1/chat/completions is supported")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        control = get_mock_control(payload)
        if control["delay"] > 0:
            time.sleep(control["delay"])
        if control["error"]:
            error_payload, status = build_error_response(control["error"])
            self._send_json(error_payload, status=status)
            return

        model = payload.get("model", "mock-chat")
        content = choose_response(payload)
        if payload.get("stream"):
            self._send_stream(model, content)
        else:
            self._send_json(build_chat_completion(model, content))

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[mock-openai] {self.address_string()} - {format % args}")

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def _send_stream(self, model: str, content: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        for event in iter_stream_events(model, content):
            self.wfile.write(event.encode("utf-8"))
            self.wfile.flush()


def run_server(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), MockOpenAIHandler)
    print(f"Mock OpenAI server listening on http://{host}:{port}")
    print("Chat completions endpoint: /v1/chat/completions")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down mock server...")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local OpenAI-compatible mock server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
