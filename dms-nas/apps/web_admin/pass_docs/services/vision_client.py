"""
Клиент Ollama для vision-моделей: JSON-ответ, картинки через base64.

Переменные окружения:
  OLLAMA_BASE_URL — по умолчанию http://127.0.0.1:11434
  OLLAMA_MODEL — по умолчанию qwen2.5vl:32b
  OLLAMA_READ_TIMEOUT — таймаут чтения ответа (сек), по умолчанию 300 при наличии картинок, иначе 120
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
    timeout: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """
    POST /api/chat с format=json.
    images_b64 — список base64-строк (без префикса data:), передаются в первом user-сообщении.
    """
    if timeout is None:
        read_default = 300.0 if images_b64 else 120.0
        raw = os.environ.get("OLLAMA_READ_TIMEOUT", "").strip()
        read_t = float(raw) if raw else read_default
        timeout = (15.0, read_t)

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

    if images_b64:
        logger.info(
            "Ollama vision: model=%s images=%s read_timeout=%ss",
            OLLAMA_MODEL,
            len(images_b64),
            timeout[1],
        )

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        if resp.status_code >= 400:
            body = (resp.text or "").strip().replace("\n", " ")
            # error: чаще видно в консоли manage.py, чем warning
            logger.error(
                "Ollama HTTP %s (первые 1200 символов тела ответа): %.1200s",
                resp.status_code,
                body,
            )
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
