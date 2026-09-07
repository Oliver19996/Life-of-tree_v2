from __future__ import annotations

import io
import secrets
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import MAX_UPLOAD_BYTES, UPLOAD_DIR

ALLOWED = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


class ImageRejected(ValueError):
    pass


def save_image(data: bytes, declared_mime: str) -> tuple[str, str, str, int, int]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageRejected("file_too_large")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageRejected("invalid_image") from exc
    fmt = ALLOWED.get(declared_mime)
    if img.format and img.format not in {"JPEG", "PNG", "WEBP", None}:
        raise ImageRejected("unsupported_type")
    if declared_mime not in ALLOWED:
        # trust actual decoded image, still reject exotic formats
        if img.format not in {"JPEG", "PNG", "WEBP", None}:
            raise ImageRejected("unsupported_type")
        fmt = "JPEG"
        mime = "image/jpeg"
    else:
        mime = declared_mime
        fmt = ALLOWED[mime]
    key = secrets.token_urlsafe(24)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    full_name = f"{key}.jpg"
    thumb_name = f"{key}_t.jpg"
    full_path = UPLOAD_DIR / full_name
    thumb_path = UPLOAD_DIR / thumb_name
    img.save(full_path, "JPEG", quality=88, optimize=True, exif=b"")
    thumb = img.copy()
    thumb.thumbnail((320, 320))
    thumb.save(thumb_path, "JPEG", quality=82, optimize=True, exif=b"")
    return full_name, thumb_name, "image/jpeg", img.width, img.height


def media_path(name: str) -> Path:
    safe = Path(name).name
    return UPLOAD_DIR / safe
