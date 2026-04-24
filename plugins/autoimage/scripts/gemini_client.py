#!/usr/bin/env python3
"""
gemini_client.py — thin wrapper around
POST /v1beta/models/<model>:generateContent for
`gemini-3.1-flash-image-preview` (Nano Banana 3.1).

Returns raw image bytes (PNG) + metadata on success.
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


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.1-flash-image-preview"
FALLBACK_MODEL = "gemini-2.5-flash-image"

# Gemini image aspect ratios supported by Nano Banana 3.1
# (used as hint in prompt; native parameter differs across API versions)
ASPECT_RATIOS = {
    "1:1": (1024, 1024),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "4:3": (1184, 880),
    "3:4": (880, 1184),
    "3:2": (1248, 832),
    "2:3": (832, 1248),
}


@dataclass
class GeminiImageResult:
    image_bytes: bytes
    model: str
    aspect_ratio: str
    finish_reason: Optional[str]


class GeminiError(RuntimeError):
    def __init__(self, status: int, message: str, body: str = ""):
        super().__init__(f"Gemini API error {status}: {message}")
        self.status = status
        self.message = message
        self.body = body


def _endpoint(model: str) -> str:
    return f"{GEMINI_BASE}/{model}:generateContent"


def _pick_aspect(width: int, height: int) -> str:
    if width == height:
        return "1:1"
    ratio = width / max(1, height)
    best_name, best_delta = "1:1", 999.0
    for name, (w, h) in ASPECT_RATIOS.items():
        d = abs((w / h) - ratio)
        if d < best_delta:
            best_delta = d
            best_name = name
    return best_name


def _request(url: str, body: dict, api_key: str, timeout: int = 120) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
            "User-Agent": "autoimage-claude/0.2.3",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _extract_image(data: dict) -> Optional[bytes]:
    for cand in data.get("candidates") or []:
        parts = ((cand.get("content") or {}).get("parts")) or []
        for p in parts:
            inline = p.get("inline_data") or p.get("inlineData")
            if inline:
                b64 = inline.get("data")
                if b64:
                    return base64.b64decode(b64)
    return None


def _finish_reason(data: dict) -> Optional[str]:
    for cand in data.get("candidates") or []:
        reason = cand.get("finishReason") or cand.get("finish_reason")
        if reason:
            return reason
    return None


def generate(
    prompt: str,
    api_key: str,
    *,
    width: int = 1024,
    height: int = 1024,
    model: str = DEFAULT_MODEL,
    max_retries: int = 3,
) -> GeminiImageResult:
    if not api_key:
        raise GeminiError(401, "GEMINI_API_KEY missing")

    aspect = _pick_aspect(width, height)
    body = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
            "imageConfig": {"aspectRatio": aspect},
        },
    }

    last_err: Optional[Exception] = None
    current_model = model
    for attempt in range(max_retries):
        try:
            data = _request(_endpoint(current_model), body, api_key)
            img = _extract_image(data)
            if not img:
                reason = _finish_reason(data)
                if reason == "IMAGE_SAFETY":
                    raise GeminiError(400, "Response blocked by safety filter (IMAGE_SAFETY)")
                raise GeminiError(500, f"Gemini returned no image (finishReason={reason})")
            return GeminiImageResult(
                image_bytes=img,
                model=current_model,
                aspect_ratio=aspect,
                finish_reason=_finish_reason(data),
            )
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            last_err = e
            if e.code == 404 and current_model == DEFAULT_MODEL:
                # 3.1 preview not available on this key tier — fall back
                current_model = FALLBACK_MODEL
                continue
            if e.code == 429 or 500 <= e.code < 600:
                wait = min(16.0, (2 ** attempt) + random.random())
                time.sleep(wait)
                continue
            raise GeminiError(e.code, str(e), body_text) from e
        except urllib.error.URLError as e:
            last_err = e
            time.sleep(min(16.0, (2 ** attempt) + random.random()))
            continue

    raise GeminiError(0, f"Gemini request failed after {max_retries} attempts: {last_err}")
