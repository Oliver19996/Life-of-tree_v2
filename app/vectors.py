from __future__ import annotations

import hashlib
import json

import numpy as np

from .taxonomy import GRAINS, LIMBS


def embed_text(role_input: str, limb_id: str, bough_id: str, grain_id: str) -> list[float]:
    limb_ids = [x["id"] for x in LIMBS]
    bough_idx = int(bough_id.replace("b", "") or "1") - 1
    grain_ids = [x["id"] for x in GRAINS]
    vec = np.zeros(15 + 10 + 5 + 32, dtype=np.float32)
    if limb_id in limb_ids:
        vec[limb_ids.index(limb_id)] = 3.0
    vec[15 + max(0, min(9, bough_idx))] = 2.0
    if grain_id in grain_ids:
        vec[25 + grain_ids.index(grain_id)] = 2.5
    blob = role_input.encode("utf-8")
    for i in range(32):
        h = hashlib.blake2b(blob + bytes([i]), digest_size=8).digest()
        vec[30 + i] = int.from_bytes(h, "little") / 2**64
    n = np.linalg.norm(vec) or 1.0
    return (vec / n).tolist()


def dumps(vec: list[float]) -> str:
    return json.dumps(vec)


def loads(raw: str) -> np.ndarray:
    return np.array(json.loads(raw), dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return float(np.dot(a, b) / denom)
