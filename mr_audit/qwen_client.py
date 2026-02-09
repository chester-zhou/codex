from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import requests


JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> Dict[str, Any]:
    match = JSON_RE.search(text)
    if not match:
        raise ValueError("未找到 JSON 结构")
    return json.loads(match.group(0))


def call_qwen_json(
    system_prompt: str,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 1024,
    timeout: int = 60,
) -> Dict[str, Any]:
    api_key = os.getenv("QWEN_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 QWEN_API_KEY 环境变量")

    base_url = os.getenv("QWEN_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model_name = model or os.getenv("QWEN_MODEL", "qwen-plus")

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"Qwen API 请求失败: {resp.status_code} {resp.text}")

    data = resp.json()
    content = ""
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        content = json.dumps(data, ensure_ascii=False)

    return extract_json(content)
