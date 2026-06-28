#!/usr/bin/env python
"""Run a deterministic RAG generation-review-revision E2E check against mock OpenAI.

Prerequisites:
    python tools/mock_openai_server.py --port 9000
    python manage.py runserver 127.0.0.1:8000 --noreload

The script temporarily points active writer/reviewer configs to the mock server
and restores them before exit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, Any


def post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: int = 20) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str, headers: Dict[str, str], timeout: int = 20) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TestFusion mock AI E2E check.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--mock-base", default="http://127.0.0.1:9000")
    parser.add_argument("--poll-seconds", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    import django
    django.setup()

    from apps.requirement_analysis.models import AIModelConfig, TestCaseGenerationTask
    from apps.users.models import User
    from rest_framework_simplejwt.tokens import RefreshToken

    configs = list(AIModelConfig.objects.filter(role__in=["writer", "reviewer"], is_active=True))
    if not configs:
        print("No active writer/reviewer AI configs found.", file=sys.stderr)
        return 1

    original = {
        config.id: {
            "base_url": config.base_url,
            "model_name": config.model_name,
            "api_key": config.api_key,
        }
        for config in configs
    }

    task_id = None
    try:
        for config in configs:
            config.base_url = args.mock_base
            config.model_name = "mock-chat"
            config.api_key = "mock-key"
            config.save(update_fields=["base_url", "model_name", "api_key"])

        token = str(RefreshToken.for_user(User.objects.get(username="admin")).access_token)
        auth_headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "title": f"MOCK-E2E-RAG-review-{int(time.time())}",
            "requirement_text": (
                "登录功能：用户名为6到20位字母数字组合；密码必须包含大小写字母和数字，长度8到32位；"
                "连续5次登录失败锁定账号30分钟；验证码有效期5分钟。"
            ),
            "use_writer_model": True,
            "use_reviewer_model": True,
            "output_mode": "complete",
        }

        created = post_json(
            f"{args.api_base}/api/requirement-analysis/testcase-generation/generate/",
            payload,
            auth_headers,
        )
        task_id = created["task"]["task_id"]
        print(f"TASK_ID {task_id}")

        deadline = time.time() + args.timeout_seconds
        while time.time() < deadline:
            time.sleep(args.poll_seconds)
            data = get_json(
                f"{args.api_base}/api/requirement-analysis/testcase-generation/{task_id}/",
                auth_headers,
            )
            print(
                "POLL",
                data["status"],
                data["progress"],
                len(data.get("generated_test_cases") or ""),
                len(data.get("review_feedback") or ""),
                len(data.get("final_test_cases") or ""),
            )
            if data["status"] in ("completed", "failed", "cancelled"):
                break
        else:
            print("Timed out waiting for task completion.", file=sys.stderr)
            return 1

        task = TestCaseGenerationTask.objects.get(task_id=task_id)
        checks = {
            "completed": task.status == "completed",
            "rag_context_present": len(task.rag_context or "") > 20,
            "generation_mocked": "MOCKTC001" in (task.generated_test_cases or ""),
            "review_mocked": "Mock" in (task.review_feedback or "") and "RAG" in (task.review_feedback or ""),
            "final_present": len(task.final_test_cases or "") > 20,
        }
        for name, passed in checks.items():
            print(f"CHECK {name} {passed}")
        if not all(checks.values()):
            return 1

        print("MOCK_E2E_OK")
        return 0
    finally:
        for config in configs:
            saved = original[config.id]
            config.base_url = saved["base_url"]
            config.model_name = saved["model_name"]
            config.api_key = saved["api_key"]
            config.save(update_fields=["base_url", "model_name", "api_key"])
        print("CONFIG_RESTORED")


if __name__ == "__main__":
    raise SystemExit(main())
