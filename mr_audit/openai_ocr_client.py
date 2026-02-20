from __future__ import annotations

import base64
import io
import json
import os
import re
from typing import Any, Dict

import requests


JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Dict[str, Any]:
    match = JSON_RE.search(text)
    if not match:
        raise ValueError("未找到 JSON 结构")
    return json.loads(match.group(0))


def _get_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY 环境变量")
    return api_key


def openai_ocr_image(
    image,
    *,
    prompt: str | None = None,
    min_pixels: int = 32 * 32 * 3,
    max_pixels: int = 32 * 32 * 8192,
    timeout: int = 90,
) -> str:
    api_key = _get_api_key()
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model_name = os.getenv("OPENAI_OCR_MODEL", "gpt-4.1-mini")

    if prompt is None:
        prompt = '请识别图片中的全部文字，仅输出 JSON，格式为: {"text": "..."}。'

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    data_url = f"data:image/png;base64,{encoded}"

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": data_url,
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},
    }

    # Keep compatibility with OpenAI-like gateways that accept these optional fields.
    payload["extra_body"] = {
        "min_pixels": min_pixels,
        "max_pixels": max_pixels,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI OCR 请求失败: {resp.status_code} {resp.text}")

    data = resp.json()
    content = ""
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        content = json.dumps(data, ensure_ascii=False)

    result = _extract_json(content)
    return str(result.get("text", "")).strip()
