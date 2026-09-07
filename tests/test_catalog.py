"""Catalog integrity tests."""

import json
from pathlib import Path

from app.catalog import load_raw
from app.db import SessionLocal, TaxonomyBranch, TaxonomyLeaf, TaxonomyTrunk, init_db
from sqlalchemy import func, select


def test_raw_catalog_shape():
    data = load_raw()
    assert len(data["trunks"]) == 5
    assert len(data["branches"]) == 35
    assert len(data["leaves"]) == 350
    ids = [x["id"] for x in data["leaves"]]
    assert len(set(ids)) == 350
    for leaf in data["leaves"]:
        assert leaf["label_short_ja"]
        assert leaf["description_ja"]
        assert leaf["id"].startswith(leaf["branch_id"])
        parent = next(b for b in data["branches"] if b["id"] == leaf["branch_id"])
        assert parent["trunk_id"] == leaf["id"][:3]


def test_seeded_database(tmp_path, monkeypatch):
    init_db()
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count()).select_from(TaxonomyTrunk)) == 5
        assert db.scalar(select(func.count()).select_from(TaxonomyBranch)) == 35
        assert db.scalar(select(func.count()).select_from(TaxonomyLeaf)) == 350
    finally:
        db.close()
