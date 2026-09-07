from __future__ import annotations

import re
import unicodedata

CRISIS_TERMS = ("死にたい", "自殺", "消えたい", "自傷")
HIGH_RISK = (
    "死ね",
    "殺す",
    "強姦",
    "児童",
    "未成年",
    "援助交際",
    "薬物売買",
)
CONTACT = re.compile(r"(https?://|www\.|@[\w.-]+|\d{2,4}-\d{2,4}-\d{3,4}|line\s*id)", re.I)
DISCRIM = ("死ね", "部落", "障害者は")


def normalize_text(value: str, max_len: int) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = "".join(ch for ch in text if ch.isprintable())
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def crisis_in(text: str) -> bool:
    return any(term in (text or "") for term in CRISIS_TERMS)


def inspect_custom_route(trunk: str, branch: str, leaf: str) -> tuple[str, str | None]:
    blob = f"{trunk} {branch} {leaf}"
    if any(term in blob for term in HIGH_RISK):
        return "pending_review", "excluded_theme"
    if CONTACT.search(blob):
        return "pending_review", "contact_info"
    if any(term in blob for term in DISCRIM):
        return "pending_review", "abuse"
    if crisis_in(blob):
        return "pending_review", "self_harm"
    if len(leaf) < 4:
        return "pending_review", "uncertain"
    return "published", None


PUBLIC_HELPLINES = {
    "label": "公的な相談窓口",
    "items": [
        {"name": "いのちの電話", "note": "いのちの電話など、お住まいの地域の公的窓口をご利用ください。"},
        {"name": "緊急時", "note": "今すぐ危険な場合は、お住まいの地域の緊急通報をご利用ください。"},
    ],
}
