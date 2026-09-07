from __future__ import annotations

import base64
import io
import re
import secrets

import httpx
from PIL import Image

from .config import IMAGE_API_KEY, IMAGE_MODEL, IMAGE_PROVIDER, UPLOAD_DIR

PROMPT_VERSION = "v1"
SAFE_TAG = re.compile(r"^[a-zA-Z0-9-]{1,40}$")


class AiImageError(RuntimeError):
    pass


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


def generate_tree_jpeg(tags: list[str]) -> tuple[bytes, str]:
    if IMAGE_PROVIDER.lower() != "openai" or not IMAGE_API_KEY:
        raise AiImageError("ai_unavailable")
    prompt = build_prompt(tags)
    headers = {"Authorization": f"Bearer {IMAGE_API_KEY}", "Content-Type": "application/json"}
    payload: dict = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
    }
    if IMAGE_MODEL.startswith("dall-e"):
        payload["response_format"] = "b64_json"
        payload["quality"] = "standard"
    try:
        with httpx.Client(timeout=90.0) as client:
            res = client.post("https://api.openai.com/v1/images/generations", headers=headers, json=payload)
            if res.status_code >= 400:
                raise AiImageError("ai_provider_failed")
            body = res.json()
            item = (body.get("data") or [{}])[0]
            raw = b""
            if item.get("b64_json"):
                raw = base64.b64decode(item["b64_json"])
            elif item.get("url"):
                fetched = client.get(item["url"], timeout=90.0)
                if fetched.status_code >= 400:
                    raise AiImageError("ai_provider_failed")
                raw = fetched.content
            if not raw:
                raise AiImageError("ai_provider_failed")
    except httpx.HTTPError as exc:
        raise AiImageError("ai_provider_failed") from exc
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue(), IMAGE_MODEL


def save_tree_jpeg(data: bytes) -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"ai_{secrets.token_urlsafe(16)}.jpg"
    (UPLOAD_DIR / name).write_bytes(data)
    return name
