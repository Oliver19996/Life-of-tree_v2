from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import get_leaf_map, trunk_of
from .config import GROWTH_RULE_VERSION
from .db import (
    CustomRoute,
    GrowthSnapshot,
    Reaction,
    RouteAdoption,
    TaxonomyLeaf,
    TreeSelection,
    TreeVersion,
    utcnow,
)
from .tree_svg import GROWTH_NAMES, growth_stage, render_tree_svg


def current_versions(db: Session, user_id: int) -> tuple[TreeVersion | None, TreeVersion | None]:
    draft = db.scalar(
        select(TreeVersion)
        .where(TreeVersion.user_id == user_id, TreeVersion.status == "draft")
        .order_by(TreeVersion.version_no.desc())
    )
    published = db.scalar(
        select(TreeVersion)
        .where(TreeVersion.user_id == user_id, TreeVersion.status == "published")
        .order_by(TreeVersion.version_no.desc())
    )
    return draft, published


def ensure_draft(db: Session, user_id: int) -> TreeVersion:
    draft, published = current_versions(db, user_id)
    if draft:
        return draft
    next_no = 1
    if published:
        next_no = published.version_no + 1
        draft = TreeVersion(user_id=user_id, version_no=next_no, status="draft")
        db.add(draft)
        db.flush()
        for sel in db.scalars(select(TreeSelection).where(TreeSelection.tree_version_id == published.id)):
            db.add(TreeSelection(tree_version_id=draft.id, leaf_id=sel.leaf_id))
        db.flush()
        refresh_svg(db, draft)
        return draft
    draft = TreeVersion(user_id=user_id, version_no=next_no, status="draft")
    db.add(draft)
    db.flush()
    refresh_svg(db, draft)
    return draft


def leaf_ids_of(db: Session, tree_version_id: int) -> list[str]:
    return list(
        db.scalars(select(TreeSelection.leaf_id).where(TreeSelection.tree_version_id == tree_version_id)).all()
    )


def published_leaf_ids(db: Session, user_id: int) -> set[str]:
    _, published = current_versions(db, user_id)
    if not published:
        return set()
    return set(leaf_ids_of(db, published.id))


def trunk_progress(leaf_ids: list[str]) -> dict[str, int]:
    counts = {f"T0{i}": 0 for i in range(1, 6)}
    for lid in leaf_ids:
        t = trunk_of(lid)
        if t in counts:
            counts[t] += 1
    return counts


def missing_trunks(leaf_ids: list[str]) -> list[str]:
    progress = trunk_progress(leaf_ids)
    return [tid for tid, n in progress.items() if n < 1]


def refresh_svg(db: Session, tree: TreeVersion) -> None:
    ids = leaf_ids_of(db, tree.id)
    snap = db.get(GrowthSnapshot, tree.user_id)
    stage = snap.growth_stage if snap else 1
    tree.svg_body = render_tree_svg(ids, tree.version_no, stage=stage)
    tree.svg_url = f"/api/v1/trees/{tree.user_id}/svg?v={tree.version_no}&s={tree.status}"


def set_selections(db: Session, tree: TreeVersion, leaf_ids: list[str]) -> None:
    leaves = get_leaf_map(db)
    unique = []
    seen = set()
    for lid in leaf_ids:
        if lid in seen:
            continue
        if lid not in leaves:
            raise ValueError("unknown_leaf")
        seen.add(lid)
        unique.append(lid)
    existing = db.scalars(select(TreeSelection).where(TreeSelection.tree_version_id == tree.id)).all()
    for row in existing:
        db.delete(row)
    db.flush()
    for lid in unique:
        db.add(TreeSelection(tree_version_id=tree.id, leaf_id=lid))
    db.flush()
    refresh_svg(db, tree)


def publish_tree(db: Session, user_id: int) -> TreeVersion:
    draft = ensure_draft(db, user_id)
    ids = leaf_ids_of(db, draft.id)
    missing = missing_trunks(ids)
    if missing:
        raise ValueError("incomplete:" + ",".join(missing))
    # keep old published for history; mark this one published
    draft.status = "published"
    draft.published_at = utcnow()
    refresh_svg(db, draft)
    # new empty draft copy for future edits
    nxt = TreeVersion(user_id=user_id, version_no=draft.version_no + 1, status="draft")
    db.add(nxt)
    db.flush()
    for lid in ids:
        db.add(TreeSelection(tree_version_id=nxt.id, leaf_id=lid))
    db.flush()
    refresh_svg(db, nxt)
    return draft


def recalc_growth(db: Session, owner_id: int) -> GrowthSnapshot:
    rows = db.scalars(
        select(Reaction).where(Reaction.owner_user_id == owner_id, Reaction.active.is_(True))
    ).all()
    count = len(rows)
    stage = growth_stage(count)
    snap = db.get(GrowthSnapshot, owner_id)
    if not snap:
        snap = GrowthSnapshot(user_id=owner_id)
        db.add(snap)
    snap.valid_reaction_count = count
    snap.growth_stage = stage
    snap.growth_rule_version = GROWTH_RULE_VERSION
    snap.calculated_at = utcnow()
    draft, published = current_versions(db, owner_id)
    if published:
        refresh_svg(db, published)
    if draft:
        refresh_svg(db, draft)
    return snap


def adopted_route_ids(db: Session, user_id: int) -> set[int]:
    return set(
        db.scalars(
            select(RouteAdoption.origin_route_id).where(
                RouteAdoption.user_id == user_id, RouteAdoption.active.is_(True)
            )
        ).all()
    )


def growth_name_only(db: Session, user_id: int) -> dict:
    snap = db.get(GrowthSnapshot, user_id)
    stage = snap.growth_stage if snap else 1
    return {"stage": stage, "name": GROWTH_NAMES[stage]}


def leaf_visual_tags(db: Session, leaf_ids: list[str]) -> list[str]:
    tags: list[str] = []
    for lid in leaf_ids:
        leaf = db.get(TaxonomyLeaf, lid)
        if not leaf:
            continue
        for tag in json.loads(leaf.visual_tags_json or "[]"):
            if tag not in tags:
                tags.append(tag)
    return tags
