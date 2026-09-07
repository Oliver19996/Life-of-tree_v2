from __future__ import annotations

import base64
import io
import logging
import re
import secrets

import httpx
from PIL import Image

from .config import IMAGE_API_KEY, IMAGE_MODEL, IMAGE_PROVIDER, UPLOAD_DIR

PROMPT_VERSION = "v1"
SAFE_TAG = re.compile(r"^[a-zA-Z0-9-]{1,40}$")
log = logging.getLogger("tof")


class AiImageError(RuntimeError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def sanitize_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for tag in tags:
        if isinstance(tag, str) and SAFE_TAG.match(tag) and tag not in out:
            out.append(tag)
        if len(out) >= 12:
            break
    return out


def build_prompt(tags: list[str]) -> str:
    directions = ", ".join(sanitize_tags(tags)) or "balanced canopy, warm light, living wood"
    return (
        "Create a single majestic, highly detailed tree as a symbol of a lived life. "
        f"Use only these abstract art directions: {directions}. "
        "Every variation must feel dignified, harmonious, hopeful, and beautiful. "
        "Do not depict illness, injury, trauma, text, people, faces, symbols, or diagnostic meaning. "
        "No gloomy punishment metaphor. No readable labels. Centered composition, natural light."
    )


def _models_to_try() -> list[str]:
    preferred = (IMAGE_MODEL or "gpt-image-1").strip()
    models = [preferred]
    for extra in ("gpt-image-1", "dall-e-3"):
        if extra not in models:
            models.append(extra)
    return models


def _extract_image_bytes(item: dict, client: httpx.Client) -> bytes:
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        fetched = client.get(item["url"], timeout=90.0)
        if fetched.status_code >= 400:
            raise AiImageError("ai_provider_failed")
        return fetched.content
    raise AiImageError("ai_provider_failed")


def _openai_error_code(status: int, body: dict) -> str:
    err = body.get("error") or {}
    code = str(err.get("code") or "")
    message = str(err.get("message") or "").lower()
    if status in {401, 403}:
        return "ai_auth"
    if "does not exist" in message or code == "invalid_value":
        return "ai_model"
    if "billing" in message or "quota" in message or "insufficient" in message:
        return "ai_billing"
    if status == 429:
        return "ai_quota"
    return "ai_provider_failed"


def generate_tree_jpeg(tags: list[str]) -> tuple[bytes, str]:
    if IMAGE_PROVIDER.lower() != "openai" or not IMAGE_API_KEY:
        raise AiImageError("ai_unavailable")
    prompt = build_prompt(tags)
    headers = {"Authorization": f"Bearer {IMAGE_API_KEY}", "Content-Type": "application/json"}
    last_code = "ai_provider_failed"
    with httpx.Client(timeout=120.0) as client:
        for model in _models_to_try():
            payload = {"model": model, "prompt": prompt, "n": 1, "size": "1024x1024"}
            try:
                res = client.post("https://api.openai.com/v1/images/generations", headers=headers, json=payload)
            except httpx.HTTPError as exc:
                last_code = "ai_provider_failed"
                log.warning("openai image transport error model=%s type=%s", model, type(exc).__name__)
                continue
            if res.status_code >= 400:
                try:
                    body = res.json()
                except Exception:
                    body = {}
                last_code = _openai_error_code(res.status_code, body)
                log.warning("openai image http=%s model=%s code=%s", res.status_code, model, last_code)
                continue
            item = ((res.json() or {}).get("data") or [{}])[0]
            raw = _extract_image_bytes(item, client)
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            out = io.BytesIO()
            img.save(out, "JPEG", quality=88, optimize=True)
            return out.getvalue(), model
    raise AiImageError(last_code)


def save_tree_jpeg(data: bytes) -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"ai_{secrets.token_urlsafe(16)}.jpg"
    (UPLOAD_DIR / name).write_bytes(data)
    return name
