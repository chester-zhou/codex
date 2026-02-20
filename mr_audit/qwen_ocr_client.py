from __future__ import annotations

import base64
import io
import json
import os
import re
from typing import Any, Dict, Optional, Sequence

import requests


JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Dict[str, Any]:
    match = JSON_RE.search(text)
    if not match:
        raise ValueError("未找到 JSON 结构")
    return json.loads(match.group(0))


def _get_api_key() -> str:
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 QWEN_API_KEY 或 DASHSCOPE_API_KEY 环境变量")
    return api_key


def qwen_ocr_image(
    image,
    *,
    prompt: str | None = None,
    model: Optional[str] = None,
    model_fallbacks: Optional[Sequence[str]] = None,
    min_pixels: int = 32 * 32 * 3,
    max_pixels: int = 32 * 32 * 8192,
    timeout: int = 90,
) -> str:
    api_key = _get_api_key()
    base_url = os.getenv("QWEN_API_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model_name = model or os.getenv("QWEN_OCR_MODEL", "qwen-vl-ocr-latest")

    if prompt is None:
        prompt = (
            "请识别图片中的全部文字，仅输出 JSON，格式为: {\"text\": \"...\"}。"
        )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    data_url = f"data:image/png;base64,{encoded}"

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    candidates = [model_name]
    if model_fallbacks:
        candidates.extend([m for m in model_fallbacks if m and m not in candidates])

    last_error = ""
    for candidate in candidates:
        payload = {
            "model": candidate,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url,
                                "min_pixels": min_pixels,
                                "max_pixels": max_pixels,
                            },
                        },
                    ],
                }
            ],
            "temperature": 0.0,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code >= 400:
                last_error = f"{candidate}:{resp.status_code}:{resp.text}"
                continue

            data = resp.json()
            content = ""
            try:
                content = data["choices"][0]["message"]["content"]
            except Exception:
                content = json.dumps(data, ensure_ascii=False)

            result = _extract_json(content)
            return str(result.get("text", "")).strip()
        except Exception as exc:
            last_error = f"{candidate}:{type(exc).__name__}:{exc}"

    raise RuntimeError(f"Qwen OCR 所有模型都失败: {last_error}")
