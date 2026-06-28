import json
import unittest
import os
import sys

# 动态添加当前目录到 sys.path 以支持直接导入
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import mock_openai_server


class MockOpenAIServerTests(unittest.TestCase):
    def test_selects_generation_response_from_prompt(self):
        payload = {
            "messages": [
                {"role": "user", "content": "请深入分析以下登录需求文档，并设计高覆盖率的测试用例。"}
            ]
        }

        content = mock_openai_server.choose_response(payload)

        self.assertIn("MOCKTC001", content)
        self.assertIn("验证码有效期5分钟", content)
        self.assertIn("手机号验证码登录", content)

    def test_selects_generic_generation_fallback(self):
        payload = {
            "messages": [
                {"role": "user", "content": "请深入分析以下需求文档，并设计高覆盖率的测试用例。"}
            ]
        }

        content = mock_openai_server.choose_response(payload)

        self.assertIn("MOCKGEN001", content)
        self.assertIn("边界值校验", content)

    def test_selects_api_generation_scenario(self):
        payload = {
            "messages": [
                {"role": "user", "content": "请为订单接口生成接口测试用例，包含JSONPath断言。"}
            ]
        }

        content = mock_openai_server.choose_response(payload)

        self.assertIn("MOCKAPI001", content)
        self.assertIn("JSONPath", content)
        self.assertIn("状态码", content)

    def test_selects_ui_generation_scenario(self):
        payload = {
            "messages": [
                {"role": "user", "content": "请生成Playwright和Selenium适用的UI自动化测试用例。"}
            ]
        }

        content = mock_openai_server.choose_response(payload)

        self.assertIn("MOCKUI001", content)
        self.assertIn("元素定位", content)

    def test_selects_app_generation_scenario(self):
        payload = {
            "messages": [
                {"role": "user", "content": "请生成Android APP自动化测试用例，使用ADB和uiautomator2。"}
            ]
        }

        content = mock_openai_server.choose_response(payload)

        self.assertIn("MOCKAPP001", content)
        self.assertIn("设备连接", content)

    def test_selects_review_response_from_prompt(self):
        payload = {
            "messages": [
                {"role": "user", "content": "请对以下生成的测试用例进行严格的专家级评审。"}
            ]
        }

        content = mock_openai_server.choose_response(payload)

        self.assertIn("参考资料作为补充约束", content)
        self.assertIn("手机号+验证码登录", content)

    def test_selects_rag_filter_response_from_prompt(self):
        payload = {
            "messages": [
                {"role": "user", "content": "待筛选的检索片段：用户登录功能要求：验证码有效期5分钟"}
            ]
        }

        content = mock_openai_server.choose_response(payload)

        self.assertIn("用户登录功能要求", content)
        self.assertIn("验证码有效期5分钟", content)

    def test_revision_response_uses_project_friendly_case_ids(self):
        payload = {
            "messages": [
                {"role": "user", "content": "请根据以下专家评审意见，改进和完善测试用例。"}
            ]
        }

        content = mock_openai_server.choose_response(payload)

        self.assertIn("MOCKTC004", content)
        self.assertNotIn("MOCK_TC_", content)

    def test_non_stream_response_is_openai_compatible(self):
        response = mock_openai_server.build_chat_completion(
            "mock-chat",
            "固定内容",
            stream=False,
        )

        self.assertEqual(response["object"], "chat.completion")
        self.assertEqual(response["model"], "mock-chat")
        self.assertEqual(response["choices"][0]["message"]["content"], "固定内容")
        self.assertIn("usage", response)

    def test_stream_events_are_sse_chat_completion_chunks(self):
        events = list(mock_openai_server.iter_stream_events("mock-chat", "测试流式输出", chunk_size=2))

        self.assertTrue(events[-1].endswith("data: [DONE]\n\n"))
        payload = json.loads(events[0].removeprefix("data: ").strip())
        self.assertEqual(payload["object"], "chat.completion.chunk")
        self.assertEqual(payload["choices"][0]["delta"]["content"], "测试")

    def test_builds_openai_compatible_error_payload(self):
        payload, status = mock_openai_server.build_error_response("rate_limit")

        self.assertEqual(status, 429)
        self.assertEqual(payload["error"]["type"], "rate_limit_error")

    def test_detects_mock_control_from_model_and_prompt(self):
        by_model = mock_openai_server.get_mock_control({"model": "mock-error-500"})
        by_prompt = mock_openai_server.get_mock_control({
            "messages": [{"role": "user", "content": "MOCK_RATE_LIMIT"}]
        })

        self.assertEqual(by_model["error"], "server_error")
        self.assertEqual(by_prompt["error"], "rate_limit")

    def test_models_response_is_openai_compatible(self):
        response = mock_openai_server.build_models_response()

        self.assertEqual(response["object"], "list")
        self.assertTrue(any(item["id"] == "mock-chat" for item in response["data"]))


if __name__ == "__main__":
    unittest.main()
