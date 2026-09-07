from __future__ import annotations

import hashlib
import hmac
import math
from typing import Iterable

from .config import TREE_SECRET

GROWTH_NAMES = {1: "芽光", 2: "花明", 3: "星実", 4: "光冠", 5: "神樹"}


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


def collect_tags(leaf_tags: list[list[str]]) -> list[str]:
    seen: list[str] = []
    for group in leaf_tags:
        for tag in group:
            if tag not in seen:
                seen.append(tag)
    return seen[:12]


def render_tree_svg(
    leaf_ids: list[str],
    version_no: int,
    stage: int = 1,
    extra_tags: list[str] | None = None,
) -> str:
    seed = visual_seed(leaf_ids, version_no)
    count = len(leaf_ids)
    density = min(1.0, 0.12 + count * 0.018)
    hue = 140 + int(_rng(seed, 1) * 28) - 8
    crown_r = 90 + density * 70
    branch_n = 6 + int(density * 10)
    flower_n = 0 if stage < 2 else 8 + stage * 4
    fruit_n = 0 if stage < 3 else 6 + stage * 3
    halo = stage >= 4
    stardust = stage >= 5

    paths = []
    glow_paths = []
    for i in range(branch_n):
        ang = -110 + i * (220 / max(branch_n - 1, 1)) + (_rng(seed, 10 + i) - 0.5) * 12
        length = 70 + density * 90 + _rng(seed, 40 + i) * 30
        rad = math.radians(ang)
        x2 = 300 + math.sin(rad) * length
        y2 = 430 - math.cos(rad) * length
        cx = 300 + math.sin(rad) * length * 0.45 + (_rng(seed, 80 + i) - 0.5) * 40
        cy = 430 - math.cos(rad) * length * 0.4
        d = f"M 300 460 Q {cx:.1f} {cy:.1f} {x2:.1f} {y2:.1f}"
        paths.append(d)
        glow_paths.append(d)

    leaves_g = []
    for i in range(int(18 + density * 40)):
        a = _rng(seed, 200 + i) * math.tau
        r = 20 + _rng(seed, 300 + i) * crown_r
        x = 300 + math.cos(a) * r * 0.85
        y = 250 + math.sin(a) * r * 0.55
        opacity = 0.35 + _rng(seed, 400 + i) * 0.45
        size = 8 + _rng(seed, 500 + i) * 14
        leaves_g.append(
            f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{size:.1f}" ry="{size * 0.55:.1f}" '
            f'transform="rotate({int(_rng(seed, 600+i)*80-40)} {x:.1f} {y:.1f})" '
            f'fill="hsla({hue + int(_rng(seed,700+i)*20)}, 48%, {42 + _rng(seed,800+i)*18:.0f}%, {opacity:.2f})" />'
        )

    flowers = []
    for i in range(flower_n):
        a = _rng(seed, 900 + i) * math.tau
        r = 40 + _rng(seed, 910 + i) * (crown_r - 10)
        x = 300 + math.cos(a) * r * 0.8
        y = 240 + math.sin(a) * r * 0.5
        flowers.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="#F7F3E8" opacity="0.9"/>')

    fruits = []
    for i in range(fruit_n):
        a = _rng(seed, 1000 + i) * math.tau
        r = 50 + _rng(seed, 1010 + i) * (crown_r - 20)
        x = 300 + math.cos(a) * r * 0.75
        y = 255 + math.sin(a) * r * 0.48
        fruits.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.4" fill="#66E3A4" opacity="0.75"/>')

    particles = []
    if stage >= 3:
        for i in range(10 + stage * 4):
            x = 180 + _rng(seed, 1100 + i) * 240
            y = 80 + _rng(seed, 1200 + i) * 280
            particles.append(f'<circle class="particle" cx="{x:.1f}" cy="{y:.1f}" r="1.4" fill="#66E3A4" opacity="0.35"/>')

    halo_svg = ""
    if halo:
        halo_svg = '<ellipse cx="300" cy="240" rx="210" ry="150" fill="rgba(102,227,164,0.16)"/>'
    if stardust:
        halo_svg += '<ellipse cx="300" cy="230" rx="240" ry="170" fill="rgba(247,243,232,0.18)"/>'

    trunk_w = 18 + density * 10
    glow_d = " ".join(f'<path d="{d}" fill="none" stroke="#66E3A4" stroke-width="2" opacity="0.45" class="life-glow"/>' for d in glow_paths)
    branch_d = " ".join(f'<path d="{d}" fill="none" stroke="#1F6B45" stroke-width="3.2" stroke-linecap="round"/>' for d in paths)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 720" role="img" aria-hidden="true">
  <defs>
    <radialGradient id="sky" cx="50%" cy="28%" r="70%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="100%" stop-color="#F0F8F3"/>
    </radialGradient>
    <style>
      .life-glow {{ filter: url(#soft); }}
      @media (prefers-reduced-motion: reduce) {{
        .particle, .life-glow {{ animation: none !important; }}
      }}
    </style>
    <filter id="soft"><feGaussianBlur stdDeviation="1.2"/></filter>
  </defs>
  <rect width="600" height="720" fill="url(#sky)"/>
  <path d="M40 640 C 140 560, 220 680, 300 640 C 390 590, 470 690, 560 640 L 560 720 L 40 720 Z" fill="#DDF3E6" opacity="0.55"/>
  {halo_svg}
  <path d="M {300 - trunk_w/2:.1f} 680 C 292 560, 294 500, 300 430 C 306 500, 308 560, {300 + trunk_w/2:.1f} 680 Z" fill="#3A6B4F"/>
  {glow_d}
  {branch_d}
  <g>{''.join(leaves_g)}</g>
  <g>{''.join(flowers)}</g>
  <g>{''.join(fruits)}</g>
  <g>{''.join(particles)}</g>
</svg>'''
