from fastapi.testclient import TestClient

from app.db import SessionLocal, User, init_db
from app.main import app
from app.tree_svg import render_tree_svg
from app.trees import ensure_draft, set_selections
from sqlalchemy import select


def _csrf(client: TestClient) -> str:
    return client.cookies.get("tof_csrf")


def login(client: TestClient, email: str) -> None:
    r = client.post("/api/v1/auth/demo", json={"email": email})
    assert r.status_code == 200
    client.headers["X-CSRF-Token"] = _csrf(client)


def verify(client: TestClient) -> None:
    r = client.post("/api/v1/me/age-verify", json={"confirm_18": True})
    assert r.status_code == 200


def publish_min(client: TestClient, email: str, shift: int = 0) -> TestClient:
    login(client, email)
    verify(client)
    leaves = [
        f"T01-B01-L{1+shift:02d}",
        f"T02-B01-L{1+shift:02d}",
        f"T03-B01-L{1+shift:02d}",
        f"T04-B01-L{1+shift:02d}",
        f"T05-B01-L{1+shift:02d}",
    ]
    r = client.put("/api/v1/me/tree-draft/selections", json={"leaf_ids": leaves})
    assert r.status_code == 200
    assert set(r.json()["leaf_ids"]) == set(leaves)
    assert r.json()["can_publish"] is True
    r = client.post("/api/v1/me/tree-draft/publish", json={})
    assert r.status_code == 200
    return client


def test_catalog_counts():
    init_db()
    c = TestClient(app)
    login(c, "a@local.test")
    r = c.get("/api/v1/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["trunks"] == 5
    assert body["counts"]["branches"] == 35
    assert body["counts"]["leaves"] == 350
    r = c.get("/api/v1/catalog?branch_id=T01-B01")
    assert len(r.json()["leaves"]) == 10


def test_incomplete_publish_422():
    init_db()
    c = TestClient(app)
    login(c, "b@local.test")
    verify(c)
    c.put("/api/v1/me/tree-draft/selections", json={"leaf_ids": ["T01-B01-L01"]})
    r = c.post("/api/v1/me/tree-draft/publish", json={})
    assert r.status_code == 422
    assert "T02" in r.json()["missing_trunks"]


def test_timeline_idor():
    init_db()
    c = TestClient(app)
    publish_min(c, "c@local.test")
    r = c.get("/api/v1/timelines/T01-B02-L01/posts")
    assert r.status_code == 403
    r = c.get("/api/v1/timelines/T01-B01-L01/posts")
    assert r.status_code == 200


def test_svg_deterministic():
    init_db()
    db = SessionLocal()
    try:
        from app.db import get_or_create  # type: ignore
    except Exception:
        pass
    from app.main import get_or_create_user

    u = get_or_create_user(db, "svg@local.test")
    db.commit()
    d = ensure_draft(db, u.id)
    set_selections(db, d, ["T01-B01-L01", "T02-B01-L01", "T03-B01-L01", "T04-B01-L01", "T05-B01-L01"])
    first = d.svg_body
    set_selections(db, d, ["T01-B01-L01", "T02-B01-L01", "T03-B01-L01", "T04-B01-L01", "T05-B01-L01"])
    assert d.svg_body == first
    assert 'data-grown="5"' in d.svg_body
    assert "枯" not in d.svg_body
    empty = render_tree_svg([], 1)
    one = render_tree_svg(["T01-B01-L01"], 1)
    assert 'data-grown="0"' in empty
    assert 'data-grown="1"' in one
    assert empty != one
    db.close()


def test_unpublished_route_not_searchable():
    init_db()
    c = TestClient(app)
    publish_min(c, "d@local.test")
    r = c.post(
        "/api/v1/custom-routes",
        json={"trunk_text": "危険", "branch_text": "テーマ", "leaf_text": "自殺を勧める話"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "pending_review"
    s = c.get("/api/v1/custom-routes/search")
    assert all("自殺" not in x["leaf_text"] for x in s.json()["items"])
