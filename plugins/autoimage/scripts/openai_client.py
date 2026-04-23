#!/usr/bin/env python3
"""
openai_client.py — thin wrapper around POST /v1/images/generations for
`gpt-image-2`.

No external HTTP library — uses urllib so the plugin has no runtime deps
beyond Pillow. Returns raw image bytes (PNG) + metadata dict on success.
"""

from __future__ import annotations

import base64
import json
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"
OPENAI_NATIVE_SIZES = ("1024x1024", "1536x1024", "1024x1536", "auto")
OPENAI_QUALITIES = ("low", "medium", "high", "auto")
OPENAI_BACKGROUNDS = ("transparent", "opaque", "auto")


@dataclass
class OpenAIImageResult:
    image_bytes: bytes
    model: str
    size: str
    quality: str
    background: str
    revised_prompt: Optional[str]
    usage: Optional[dict]


class OpenAIError(RuntimeError):
    def __init__(self, status: int, message: str, body: str = ""):
        super().__init__(f"OpenAI API error {status}: {message}")
        self.status = status
        self.message = message
        self.body = body


def _nearest_supported_size(width: int, height: int) -> str:
    """Pick the native gpt-image-2 size closest to the requested dimensions."""
    if width == height:
        return "1024x1024"
    if width > height:
        return "1536x1024"
    return "1024x1536"


def _request(url: str, body: dict, api_key: str, timeout: int = 120) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "autoimage-claude/0.2",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def generate(
    prompt: str,
    api_key: str,
    *,
    width: int = 1024,
    height: int = 1024,
    quality: str = "high",
    transparent: bool = False,
    model: str = "gpt-image-2",
    max_retries: int = 3,
) -> OpenAIImageResult:
    if not api_key:
        raise OpenAIError(401, "OPENAI_API_KEY missing")
    if quality not in OPENAI_QUALITIES:
        quality = "high"
    size = _nearest_supported_size(width, height)
    background = "transparent" if transparent else "opaque"

    body = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "background": background,
    }

    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            data = _request(OPENAI_IMAGES_URL, body, api_key)
            entries = data.get("data") or []
            if not entries:
                raise OpenAIError(500, "OpenAI returned no image data")
            entry = entries[0]
            b64 = entry.get("b64_json")
            if not b64:
                raise OpenAIError(500, "OpenAI response missing b64_json")
            img_bytes = base64.b64decode(b64)
            return OpenAIImageResult(
                image_bytes=img_bytes,
                model=model,
                size=size,
                quality=quality,
                background=background,
                revised_prompt=entry.get("revised_prompt"),
                usage=data.get("usage"),
            )
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            last_err = e
            # Retry on 429 / 5xx only
            if e.code == 429 or 500 <= e.code < 600:
                wait = min(16.0, (2 ** attempt) + random.random())
                time.sleep(wait)
                continue
            raise OpenAIError(e.code, str(e), body_text) from e
        except urllib.error.URLError as e:
            last_err = e
            time.sleep(min(16.0, (2 ** attempt) + random.random()))
            continue

    raise OpenAIError(0, f"OpenAI request failed after {max_retries} attempts: {last_err}")
