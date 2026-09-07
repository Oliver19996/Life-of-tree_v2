from __future__ import annotations

import hashlib
import hmac
import math
from typing import Iterable

from .config import TREE_SECRET

GROWTH_NAMES = {1: "芽光", 2: "花明", 3: "星実", 4: "光冠", 5: "神樹"}

TRUNK_ARMS = [
    {"id": "T01", "x2": 108, "y2": 318, "bulge": -42},
    {"id": "T02", "x2": 188, "y2": 118, "bulge": -30},
    {"id": "T03", "x2": 300, "y2": 62, "bulge": 10},
    {"id": "T04", "x2": 412, "y2": 118, "bulge": 30},
    {"id": "T05", "x2": 492, "y2": 318, "bulge": 42},
]


def growth_stage(count: int) -> int:
    if count >= 100:
        return 5
    if count >= 50:
        return 4
    if count >= 20:
        return 3
    if count >= 5:
        return 2
    return 1


def visual_seed(leaf_ids: Iterable[str], version_no: int) -> str:
    payload = ",".join(sorted(leaf_ids)) + f"|{version_no}"
    return hmac.new(TREE_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _rng(seed: str, n: int) -> float:
    h = hashlib.sha256(f"{seed}:{n}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def trunk_counts(leaf_ids: list[str]) -> dict[str, int]:
    counts = {arm["id"]: 0 for arm in TRUNK_ARMS}
    for lid in leaf_ids:
        tid = lid.split("-")[0]
        if tid in counts:
            counts[tid] += 1
    return counts


def _taper(x0: float, y0: float, x1: float, y1: float, w0: float, w1: float, bulge: float) -> str:
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1
    nx, ny = -dy / length, dx / length
    ux, uy = dx / length, dy / length

    def pt(t: float, side: float, extra: float) -> tuple[float, float]:
        x = x0 + ux * length * t + nx * extra
        y = y0 + uy * length * t + ny * extra
        w = (w0 + (w1 - w0) * t) / 2
        return x + nx * side * w, y + ny * side * w

    a = pt(0, 1, 0)
    c1 = pt(0.35, 1, bulge)
    c2 = pt(0.7, 1, bulge * 0.4)
    tip_l = pt(1, 1, 0)
    tip_r = pt(1, -1, 0)
    c3 = pt(0.7, -1, bulge * 0.4)
    c4 = pt(0.35, -1, bulge)
    d = pt(0, -1, 0)
    return (
        f"M {a[0]:.1f} {a[1]:.1f} C {c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {tip_l[0]:.1f} {tip_l[1]:.1f} "
        f"L {tip_r[0]:.1f} {tip_r[1]:.1f} C {c3[0]:.1f} {c3[1]:.1f} {c4[0]:.1f} {c4[1]:.1f} {d[0]:.1f} {d[1]:.1f} Z"
    )


def _foliage(cx: float, cy: float, n: int, scale: float, seed: str, salt: int) -> str:
    greens = ["#2f4d28", "#3a5c32", "#4a6f3c", "#5c8348", "#6d9454", "#7eaa62", "#8fb872"]
    parts = []
    for i in range(n):
        a = _rng(seed, salt + i) * math.tau
        r = (10 + (i % 8) * 9) * scale
        x = cx + math.cos(a) * r
        y = cy + math.sin(a) * r * 0.62
        w = (7 + (i % 5) * 2) * scale
        h = (12 + (i % 4) * 3) * scale
        rot = a * 180 / math.pi + 70
        parts.append(
            f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{w:.1f}" ry="{h:.1f}" '
            f'fill="{greens[i % len(greens)]}" opacity="0.92" transform="rotate({rot:.0f} {x:.1f} {y:.1f})" />'
        )
    return "".join(parts)


def render_tree_svg(
    leaf_ids: list[str],
    version_no: int,
    stage: int = 1,
    extra_tags: list[str] | None = None,
) -> str:
    seed = visual_seed(leaf_ids, version_no)
    counts = trunk_counts(leaf_ids)
    grown = sum(1 for n in counts.values() if n >= 1)
    total_leaves = len(leaf_ids)
    stem_h = 90 + grown * 28
    trunk_w = 10 + grown * 4 + min(total_leaves, 20) * 0.4
    top = 430
    base = 680

    arms = []
    for i, arm in enumerate(TRUNK_ARMS):
        n = counts[arm["id"]]
        alive = n >= 1
        opacity = 1 if alive else 0.14
        w0 = 10 + min(n, 8) * 1.4 if alive else 5
        w1 = 4 + min(n, 8) * 0.5 if alive else 2
        path = _taper(300, top, arm["x2"], arm["y2"], w0, w1, arm["bulge"])
        leaves = ""
        if alive:
            leaves = _foliage(arm["x2"], arm["y2"] - 8, 8 + min(n, 12) * 6, 0.85 + min(n, 8) * 0.08, seed, 40 * i)
        arms.append(
            f'<g data-trunk="{arm["id"]}" data-leaves="{n}" opacity="{opacity}">'
            f'<path d="{path}" fill="#5a3a24"/>{leaves}</g>'
        )

    canopy = ""
    if grown >= 5:
        canopy = (
            _foliage(300, 168, 36 + min(total_leaves, 30), 2.1, seed, 900)
            + _foliage(210, 210, 18, 1.4, seed, 1200)
            + _foliage(390, 210, 18, 1.4, seed, 1500)
        )

    sapling = ""
    if grown == 0:
        sapling = (
            f'<path d="M 296 {base} C 298 560, 299 500, 300 {top + 40} C 301 500, 302 560, 304 {base} Z" fill="#6b4a32"/>'
            f'<ellipse cx="300" cy="{top + 28}" rx="16" ry="22" fill="#7eaa62" opacity="0.85"/>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 720" role="img" aria-hidden="true" data-grown="{grown}" data-leaves="{total_leaves}">
  <defs>
    <radialGradient id="sky" cx="50%" cy="28%" r="70%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="100%" stop-color="#F0F8F3"/>
    </radialGradient>
  </defs>
  <rect width="600" height="720" fill="url(#sky)"/>
  <ellipse cx="300" cy="690" rx="{140 + grown * 28}" ry="28" fill="#DDF3E6" opacity="0.7"/>
  {sapling}
  <path d="M {300 - trunk_w / 2:.1f} {base} C 292 {base - stem_h}, 294 {top + 40}, 300 {top} C 306 {top + 40}, 308 {base - stem_h}, {300 + trunk_w / 2:.1f} {base} Z" fill="#3A6B4F"/>
  {"".join(arms)}
  {canopy}
</svg>'''
