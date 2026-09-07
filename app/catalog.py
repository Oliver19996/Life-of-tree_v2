from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import TaxonomyBranch, TaxonomyLeaf, TaxonomyTrunk

CATALOG_PATH = Path(__file__).with_name("catalog.json")
_CACHE = None


def load_raw() -> dict:
    global _CACHE
    if _CACHE is None:
        _CACHE = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return _CACHE


def seed_catalog(db: Session) -> None:
    count = db.scalar(select(func.count()).select_from(TaxonomyLeaf)) or 0
    if count >= 350:
        return
    data = load_raw()
    existing_t = {r.id for r in db.scalars(select(TaxonomyTrunk)).all()}
    for t in data["trunks"]:
        if t["id"] not in existing_t:
            db.add(TaxonomyTrunk(**{k: t[k] for k in ("id", "label_ja", "sort_order", "active", "version")}))
    db.flush()
    existing_b = {r.id for r in db.scalars(select(TaxonomyBranch)).all()}
    for b in data["branches"]:
        if b["id"] not in existing_b:
            db.add(TaxonomyBranch(**{k: b[k] for k in ("id", "trunk_id", "label_ja", "sort_order", "active", "version")}))
    db.flush()
    existing_l = {r.id for r in db.scalars(select(TaxonomyLeaf)).all()}
    for leaf in data["leaves"]:
        if leaf["id"] in existing_l:
            continue
        db.add(
            TaxonomyLeaf(
                id=leaf["id"],
                branch_id=leaf["branch_id"],
                label_ja=leaf["description_ja"],
                label_short_ja=leaf["label_short_ja"],
                description_ja=leaf["description_ja"],
                search_terms_ja=json.dumps(leaf["search_terms_ja"], ensure_ascii=False),
                sensitivity=leaf["sensitivity"],
                timeline_enabled=leaf["timeline_enabled"],
                visual_seed=leaf["visual_seed"],
                visual_tags_json=json.dumps(leaf["visual_tags"], ensure_ascii=False),
                active=leaf["active"],
                version=leaf["version"],
            )
        )


def catalog_payload(db: Session, include_leaves_for_branch: str | None = None) -> dict:
    trunks = db.scalars(select(TaxonomyTrunk).where(TaxonomyTrunk.active.is_(True)).order_by(TaxonomyTrunk.sort_order)).all()
    branches = db.scalars(select(TaxonomyBranch).where(TaxonomyBranch.active.is_(True)).order_by(TaxonomyBranch.sort_order)).all()
    payload = {
        "trunks": [{"id": t.id, "label_ja": t.label_ja, "sort_order": t.sort_order} for t in trunks],
        "branches": [
            {"id": b.id, "trunk_id": b.trunk_id, "label_ja": b.label_ja, "sort_order": b.sort_order}
            for b in branches
        ],
        "leaves": [],
        "counts": {"trunks": len(trunks), "branches": len(branches), "leaves": 350},
    }
    if include_leaves_for_branch:
        leaves = db.scalars(
            select(TaxonomyLeaf)
            .where(TaxonomyLeaf.branch_id == include_leaves_for_branch, TaxonomyLeaf.active.is_(True))
            .order_by(TaxonomyLeaf.id)
        ).all()
        payload["leaves"] = [_leaf_public(leaf) for leaf in leaves]
    return payload


def _leaf_public(leaf: TaxonomyLeaf) -> dict:
    return {
        "id": leaf.id,
        "branch_id": leaf.branch_id,
        "label_short_ja": leaf.label_short_ja,
        "description_ja": leaf.description_ja,
        "search_terms_ja": json.loads(leaf.search_terms_ja or "[]"),
        "sensitivity": leaf.sensitivity,
        "timeline_enabled": leaf.timeline_enabled,
    }


def get_leaf_map(db: Session) -> dict[str, TaxonomyLeaf]:
    return {leaf.id: leaf for leaf in db.scalars(select(TaxonomyLeaf).where(TaxonomyLeaf.active.is_(True))).all()}


def branch_of(leaf_id: str) -> str:
    return "-".join(leaf_id.split("-")[:2])


def trunk_of(leaf_id: str) -> str:
    return leaf_id.split("-")[0]
