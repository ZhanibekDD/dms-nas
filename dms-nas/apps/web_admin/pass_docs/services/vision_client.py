"""
Клиент Ollama для vision-моделей: JSON-ответ, картинки через base64.

Переменные окружения:
  OLLAMA_BASE_URL — по умолчанию http://127.0.0.1:11434
  OLLAMA_MODEL     — по умолчанию qwen2.5vl:32b
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5vl:32b")


def file_to_base64(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("ascii")


def file_to_base64_from_bytes(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("ascii")


def chat_json(
    user_text: str,
    *,
    images_b64: list[str] | None = None,
    timeout: tuple[float, float] = (15.0, 300.0),
) -> dict[str, Any]:
    """
    POST /api/chat с format=json.
    images_b64 — список base64-строк (без префикса data:), передаются в первом user-сообщении.
    """
    url = f"{OLLAMA_BASE_URL}/api/chat"
    msg: dict[str, Any] = {"role": "user", "content": user_text}
    if images_b64:
        msg["images"] = images_b64

    payload: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "messages": [msg],
        "stream": False,
        "format": "json",
    }

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        # Не logger.exception: иначе в консоль Windows уходит полный traceback при выключенном Ollama.
        logger.warning("Ollama request failed: %s", exc)
        raise

    data = resp.json()
    content = (data.get("message") or {}).get("content") or ""
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)

    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # иногда модель оборачивает JSON в markdown
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
        raise
