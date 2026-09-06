from __future__ import annotations

import io
import os

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .db import DATA_DIR


def stylize_selfie(data: bytes, user_id: int) -> str:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img = ImageOps.fit(img, (512, 512), Image.Resampling.LANCZOS)
    img = img.filter(ImageFilter.MedianFilter(size=3))
    img = ImageEnhance.Color(img).enhance(1.35)
    img = ImageEnhance.Contrast(img).enhance(1.45)
    img = img.quantize(colors=18, method=Image.Quantize.MEDIANCUT).convert("RGB")
    img = img.filter(ImageFilter.SMOOTH_MORE)
    overlay = Image.new("RGB", img.size, (16, 64, 42))
    img = Image.blend(img, overlay, 0.12)
    out_dir = os.path.join(DATA_DIR, "avatars")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"u{user_id}.jpg")
    img.save(path, "JPEG", quality=88)
    return f"/media/avatars/u{user_id}.jpg"
