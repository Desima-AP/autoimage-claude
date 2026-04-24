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

# Fallback ladder for the flagship model. If the caller asks for
# `gpt-image-2` and the key's organization is not verified yet (OpenAI
# ID-verification requirement, returns 403 with a specific message),
# the client silently retries with the next model in the chain. All
# three accept the same request schema — same sizes, same quality
# levels, same background options.
OPENAI_FALLBACK_CHAIN = ("gpt-image-2", "gpt-image-1.5", "gpt-image-1")
_ORG_VERIFY_HINT = "organization must be verified"


ORG_VERIFY_REMEDY_URL = "https://platform.openai.com/settings/organization/general"


@dataclass
class OpenAIImageResult:
    image_bytes: bytes
    model: str                      # the model that actually produced the image
    requested_model: str             # what the caller asked for
    fallback_used: bool              # True iff model != requested_model
    fallback_reason: Optional[str]   # one-line reason, or None
    fallback_remedy_url: Optional[str]  # link the user can follow to unblock
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
            "User-Agent": "autoimage-claude/0.2.3",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _models_to_try(requested: str) -> tuple[str, ...]:
    """Return the fallback chain for `requested`. If the caller asked for
    the flagship (`gpt-image-2`), the chain degrades to `gpt-image-1.5`
    then `gpt-image-1` on org-verification failure. Any other explicit
    request is honoured without fallback.
    """
    if requested == "gpt-image-2":
        return OPENAI_FALLBACK_CHAIN
    return (requested,)


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

    last_err: Optional[Exception] = None
    fallback_reason: Optional[str] = None
    fallback_remedy: Optional[str] = None
    for current_model in _models_to_try(model):
        body = {
            "model": current_model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": quality,
            "background": background,
        }
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
                fallback_used = current_model != model
                return OpenAIImageResult(
                    image_bytes=img_bytes,
                    model=current_model,
                    requested_model=model,
                    fallback_used=fallback_used,
                    fallback_reason=fallback_reason if fallback_used else None,
                    fallback_remedy_url=fallback_remedy if fallback_used else None,
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
                last_err = OpenAIError(e.code, str(e), body_text)
                # 403 + "organization must be verified" → advance to the
                # next model in the fallback chain immediately, and
                # remember *why* so the caller can tell the user.
                if e.code == 403 and _ORG_VERIFY_HINT in body_text.lower():
                    fallback_reason = (
                        f"OpenAI organization not yet verified — "
                        f"{current_model} is gated behind the ID-verification "
                        f"step for new keys"
                    )
                    fallback_remedy = ORG_VERIFY_REMEDY_URL
                    break
                # 429 / 5xx → retry with backoff on the same model.
                if e.code == 429 or 500 <= e.code < 600:
                    wait = min(16.0, (2 ** attempt) + random.random())
                    time.sleep(wait)
                    continue
                raise OpenAIError(e.code, str(e), body_text) from e
            except urllib.error.URLError as e:
                last_err = e
                time.sleep(min(16.0, (2 ** attempt) + random.random()))
                continue

    if isinstance(last_err, OpenAIError):
        raise last_err
    raise OpenAIError(0, f"OpenAI request failed: {last_err}")
