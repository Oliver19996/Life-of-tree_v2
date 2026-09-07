from __future__ import annotations

import json
import logging
import secrets
import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Optional
from urllib.parse import urlencode

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from .ai_image import AiImageError, PROMPT_VERSION, generate_tree_jpeg, save_tree_jpeg
from .catalog import branch_of, catalog_payload, get_leaf_map, trunk_of
from .config import (
    AI_DAILY_LIMIT,
    APP_SECRET,
    CSRF_COOKIE,
    DEMO_LOGIN,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    IMAGE_API_KEY,
    IMAGE_PROVIDER,
    SESSION_COOKIE,
    TERMS_VERSION,
    UPLOAD_DIR,
)
from .db import (
    AiJob,
    AuditLog,
    TaxonomyLeaf,
    Block,
    Comment,
    ConnectionRequest,
    CustomRoute,
    Friendship,
    MagicLink,
    Message,
    ModerationAction,
    Post,
    PostImage,
    Profile,
    Reaction,
    Report,
    RouteAdoption,
    SessionLocal,
    Thread,
    ThreadMember,
    TreeDecoration,
    TreeVersion,
    User,
    get_db,
    init_db,
    utcnow,
)
from .images import ImageRejected, media_path, save_image
from .moderation import PUBLIC_HELPLINES, crisis_in, inspect_custom_route, normalize_text
from .similarity import qualifies, resonance_label, similarity
from .trees import (
    adopted_route_ids,
    current_versions,
    ensure_draft,
    growth_name_only,
    leaf_ids_of,
    leaf_visual_tags,
    missing_trunks,
    publish_tree,
    published_leaf_ids,
    recalc_growth,
    set_selections,
    trunk_progress,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("tof")
STATIC = Path(__file__).parent / "static"
signer = URLSafeTimedSerializer(APP_SECRET, salt="tof-session")

RATE: dict[str, list[float]] = {}
JSON_BODY: ContextVar[dict] = ContextVar("json_body", default={})


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        log.info(json.dumps({"request_id": rid, "method": request.method, "path": request.url.path}))
        return response


app = FastAPI(title="Tree of Life")
app.add_middleware(RequestIdMiddleware)


@app.on_event("startup")
def _startup():
    init_db()


def error(code: str, status: int, **extra):
    return JSONResponse({"error": code, **extra}, status_code=status)


def set_session(response: Response, user_id: int) -> str:
    token = signer.dumps({"uid": user_id, "n": secrets.token_hex(8)})
    csrf = secrets.token_urlsafe(24)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=False, max_age=60 * 60 * 24 * 14)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, samesite="lax", secure=False, max_age=60 * 60 * 24 * 14)
    return csrf


def read_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        data = signer.loads(token, max_age=60 * 60 * 24 * 14)
    except BadSignature:
        return None
    user = db.get(User, data.get("uid"))
    if not user or user.status == "deleted":
        return None
    return user


def require_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    user = read_user(request, db)
    if not user:
        raise HTTPException(401, "unauthorized")
    return user


def check_csrf(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    header = request.headers.get("x-csrf-token")
    cookie = request.cookies.get(CSRF_COOKIE)
    if not header or not cookie or header != cookie:
        raise HTTPException(403, "csrf")


def rate_limit(key: str, limit: int, window: float = 60.0) -> None:
    import time

    now = time.time()
    bucket = [t for t in RATE.get(key, []) if now - t < window]
    if len(bucket) >= limit:
        raise HTTPException(429, "rate_limited")
    bucket.append(now)
    RATE[key] = bucket


def blocked_ids(db: Session, user_id: int) -> set[int]:
    rows = db.scalars(
        select(Block).where(or_(Block.blocker_id == user_id, Block.blocked_id == user_id))
    ).all()
    out: set[int] = set()
    for row in rows:
        out.add(row.blocker_id if row.blocked_id == user_id else row.blocked_id)
    return out


def is_blocked(db: Session, a: int, b: int) -> bool:
    return db.scalar(
        select(Block).where(
            or_(
                and_(Block.blocker_id == a, Block.blocked_id == b),
                and_(Block.blocker_id == b, Block.blocked_id == a),
            )
        )
    ) is not None


def are_friends(db: Session, a: int, b: int) -> bool:
    lo, hi = sorted((a, b))
    return db.scalar(select(Friendship).where(Friendship.user_low_id == lo, Friendship.user_high_id == hi)) is not None


def sns_ready(user: User, db: Session) -> bool:
    if not user.age_verified_at:
        return False
    _, published = current_versions(db, user.id)
    return published is not None


def public_profile(db: Session, user: User, viewer: User | None, for_friend: bool = False) -> dict:
    profile = user.profile
    name = profile.display_name if profile and profile.display_name else "名前未設定"
    blurb = ""
    vis = profile.blurb_visibility if profile else "friends"
    if profile:
        if vis == "public" or (vis == "friends" and (for_friend or (viewer and viewer.id == user.id))):
            blurb = profile.blurb
        if viewer and viewer.id == user.id:
            blurb = profile.blurb
    _, published = current_versions(db, user.id)
    tree_url = None
    if published:
        tree_url = published.ai_image_url or f"/api/v1/media/tree/{published.id}.svg"
    return {
        "id": user.id,
        "display_name": name,
        "avatar_url": profile.avatar_url if profile else None,
        "blurb": blurb,
        "tree_url": tree_url,
    }


def audit(db: Session, actor_id: int | None, action: str, target_type: str, target_id: str, meta: dict | None = None):
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            metadata_json=json.dumps(meta or {}),
        )
    )


def get_or_create_user(db: Session, email: str, google_sub: str | None = None) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user:
        if google_sub and not user.google_sub:
            user.google_sub = google_sub
        return user
    user = User(email=email.lower(), google_sub=google_sub, is_admin=email.lower().endswith("@local.test"))
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, display_name=email.split("@")[0][:20]))
    return user


# ---------- auth ----------


@app.post("/api/v1/auth/demo")
def auth_demo(request: Request, db: Session = Depends(get_db)):
    if not DEMO_LOGIN:
        return error("demo_disabled", 404)
    body = _json(request)
    email = (body.get("email") or "demo@local.test").strip().lower()
    user = get_or_create_user(db, email)
    db.commit()
    resp = JSONResponse({"ok": True, "user_id": user.id, "demo": True})
    set_session(resp, user.id)
    return resp


@app.post("/api/v1/auth/magic-link")
async def magic_request(request: Request, db: Session = Depends(get_db)):
    rate_limit(f"magic:{request.client.host if request.client else 'x'}", 8)
    email = normalize_text((_json(request).get("email") or ""), 320).lower()
    if "@" not in email:
        return error("invalid_email", 422)
    token = secrets.token_urlsafe(32)
    db.add(MagicLink(email=email, token=token, expires_at=utcnow() + timedelta(minutes=20)))
    db.commit()
    link = f"/api/v1/auth/magic-link/consume?token={token}"
    return {"ok": True, "dev_link": link if DEMO_LOGIN else None}


@app.get("/api/v1/auth/magic-link/consume")
def magic_consume(token: str, db: Session = Depends(get_db)):
    row = db.scalar(select(MagicLink).where(MagicLink.token == token, MagicLink.used.is_(False)))
    if not row or row.expires_at < utcnow():
        raise HTTPException(400, "invalid_token")
    row.used = True
    user = get_or_create_user(db, row.email)
    db.commit()
    resp = RedirectResponse("/", status_code=303)
    set_session(resp, user.id)
    return resp


@app.get("/api/v1/auth/google/start")
def google_start(request: Request):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(404, "google_disabled")
    redirect = str(request.base_url) + "api/v1/auth/google/callback"
    qs = urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "openid email",
            "access_type": "online",
        }
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{qs}")


@app.get("/api/v1/auth/google/callback")
def google_callback(code: str, request: Request, db: Session = Depends(get_db)):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(404, "google_disabled")
    redirect = str(request.base_url) + "api/v1/auth/google/callback"
    token_resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    token_resp.raise_for_status()
    access = token_resp.json()["access_token"]
    info = httpx.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access}"}, timeout=20)
    info.raise_for_status()
    data = info.json()
    user = get_or_create_user(db, data["email"], google_sub=data.get("id"))
    db.commit()
    resp = RedirectResponse("/", status_code=303)
    set_session(resp, user.id)
    return resp


@app.post("/api/v1/auth/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE)
    resp.delete_cookie(CSRF_COOKIE)
    return resp


@app.get("/api/v1/me")
def me(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    profile = user.profile
    draft, published = current_versions(db, user.id)
    return {
        "id": user.id,
        "email": user.email,
        "is_admin": user.is_admin,
        "age_verified": bool(user.age_verified_at),
        "terms_version": user.terms_version,
        "sns_ready": sns_ready(user, db),
        "demo_login": DEMO_LOGIN,
        "google_enabled": bool(GOOGLE_CLIENT_ID),
        "ai_enabled": bool(IMAGE_PROVIDER and IMAGE_API_KEY),
        "profile": {
            "display_name": profile.display_name if profile else "",
            "blurb": profile.blurb if profile else "",
            "blurb_visibility": profile.blurb_visibility if profile else "friends",
            "avatar_url": profile.avatar_url if profile else None,
            "reaction_notify": user.reaction_notify,
        },
        "has_published_tree": published is not None,
        "published_version_no": published.version_no if published else None,
        "ai_image_url": published.ai_image_url if published else None,
        "csrf": request.cookies.get(CSRF_COOKIE),
        "growth": growth_name_only(db, user.id) if published else None,
    }


@app.post("/api/v1/me/age-verify")
def age_verify(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    body = _json(request)
    if body.get("confirm_18") is True:
        user.age_verified_at = utcnow()
        user.terms_version = TERMS_VERSION
        db.commit()
        return {"ok": True}
    birth = body.get("birthdate")
    try:
        y, m, d = [int(x) for x in str(birth).split("-")]
        born = datetime(y, m, d, tzinfo=timezone.utc)
    except Exception:
        return error("invalid_birthdate", 422)
    today = utcnow()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if age < 18:
        return error("underage", 403)
    user.age_verified_at = utcnow()
    user.terms_version = TERMS_VERSION
    db.commit()
    return {"ok": True}


@app.put("/api/v1/me/profile")
def update_profile(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    body = _json(request)
    profile = user.profile or Profile(user_id=user.id)
    db.add(profile)
    profile.display_name = normalize_text(body.get("display_name") or "", 40)
    profile.blurb = normalize_text(body.get("blurb") or "", 400)
    vis = body.get("blurb_visibility") or profile.blurb_visibility
    if vis not in {"public", "friends", "hidden"}:
        vis = "friends"
    profile.blurb_visibility = vis
    if body.get("reaction_notify") in {"on", "digest", "off"}:
        user.reaction_notify = body["reaction_notify"]
    db.commit()
    return {"ok": True}


# ---------- catalog / tree ----------


@app.get("/api/v1/catalog")
def catalog(db: Session = Depends(get_db), user: User = Depends(require_user), branch_id: str | None = None):
    payload = catalog_payload(db, include_leaves_for_branch=branch_id)
    # full counts without dumping 350 leaves unless requested for one branch
    if not branch_id:
        payload["caution_count"] = db.scalar(
            select(func.count()).select_from(TaxonomyLeaf).where(TaxonomyLeaf.sensitivity == "caution")
        )
    return payload


@app.get("/api/v1/catalog/search")
def catalog_search(q: str = "", db: Session = Depends(get_db), user: User = Depends(require_user)):
    qn = normalize_text(q, 40)
    leaves = list(get_leaf_map(db).values())
    hits = []
    if qn:
        for leaf in leaves:
            blob = leaf.label_short_ja + leaf.description_ja + leaf.search_terms_ja
            if qn in blob:
                hits.append(
                    {
                        "id": leaf.id,
                        "branch_id": leaf.branch_id,
                        "trunk_id": trunk_of(leaf.id),
                        "label_short_ja": leaf.label_short_ja,
                        "description_ja": leaf.description_ja,
                        "sensitivity": leaf.sensitivity,
                    }
                )
            if len(hits) >= 40:
                break
    return {"q_len": len(qn), "items": hits}


@app.get("/api/v1/me/tree-draft")
def tree_draft(db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not user.age_verified_at:
        raise HTTPException(403, "age_required")
    draft = ensure_draft(db, user.id)
    db.commit()
    ids = leaf_ids_of(db, draft.id)
    progress = trunk_progress(ids)
    return {
        "version_no": draft.version_no,
        "status": draft.status,
        "leaf_ids": ids,
        "progress": {k: {"count": v, "complete": v >= 1} for k, v in progress.items()},
        "can_publish": not missing_trunks(ids),
        "svg": draft.svg_body,
        "ai_enabled": bool(IMAGE_PROVIDER and IMAGE_API_KEY),
    }


@app.put("/api/v1/me/tree-draft/selections")
def update_selections(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    if not user.age_verified_at:
        raise HTTPException(403, "age_required")
    body = _json(request)
    leaf_ids = body.get("leaf_ids") or []
    if not isinstance(leaf_ids, list) or len(leaf_ids) > 350:
        return error("invalid_selections", 422)
    draft = ensure_draft(db, user.id)
    try:
        set_selections(db, draft, [str(x) for x in leaf_ids])
    except ValueError:
        return error("unknown_leaf", 422)
    db.commit()
    ids = leaf_ids_of(db, draft.id)
    progress = trunk_progress(ids)
    return {
        "leaf_ids": ids,
        "progress": {k: {"count": v, "complete": v >= 1} for k, v in progress.items()},
        "can_publish": not missing_trunks(ids),
        "svg": draft.svg_body,
    }


@app.post("/api/v1/me/tree-draft/publish")
def do_publish(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    if not user.age_verified_at:
        raise HTTPException(403, "age_required")
    try:
        published = publish_tree(db, user.id)
    except ValueError as exc:
        missing = str(exc).split(":", 1)[-1].split(",")
        return error("incomplete_tree", 422, missing_trunks=missing)
    db.commit()
    return {"ok": True, "version_no": published.version_no, "svg_url": f"/api/v1/media/tree/{published.id}.svg"}


@app.post("/api/v1/me/tree/{version}/ai-image")
def ai_image(version: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    rate_limit(f"ai:{user.id}", AI_DAILY_LIMIT, 86400)
    if not (IMAGE_PROVIDER and IMAGE_API_KEY):
        return error("ai_unavailable", 404)
    tree = db.scalar(select(TreeVersion).where(TreeVersion.user_id == user.id, TreeVersion.version_no == version))
    if not tree or tree.status != "published":
        return error("not_found", 404)
    ids = leaf_ids_of(db, tree.id)
    tags = leaf_visual_tags(db, ids)
    job = AiJob(
        user_id=user.id,
        tree_version_id=tree.id,
        status="queued",
        provider=IMAGE_PROVIDER,
        model="",
        prompt_version=PROMPT_VERSION,
        tags_json=json.dumps(tags),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        jpeg, model = generate_tree_jpeg(tags)
        name = save_tree_jpeg(jpeg)
    except AiImageError:
        job.status = "failed"
        db.commit()
        return error("ai_provider_failed", 502, used_tags=tags, prompt_has_leaf_text=False)
    url = f"/api/v1/media/tree-ai/{name}"
    tree.ai_image_url = url
    tree.prompt_version = PROMPT_VERSION
    job.status = "succeeded"
    job.model = model
    db.commit()
    return {"ok": True, "url": url, "version_no": tree.version_no, "model": model}


@app.get("/api/v1/media/tree-ai/{name}")
def tree_ai_media(name: str, request: Request, db: Session = Depends(get_db)):
    path = media_path(name)
    if not path.exists() or not name.startswith("ai_") or not name.endswith(".jpg"):
        raise HTTPException(404)
    url = f"/api/v1/media/tree-ai/{name}"
    tree = db.scalar(select(TreeVersion).where(TreeVersion.ai_image_url == url, TreeVersion.status == "published"))
    if not tree:
        raise HTTPException(404)
    viewer = read_user(request, db)
    if viewer and is_blocked(db, viewer.id, tree.user_id):
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/v1/media/tree/{tree_id}.svg")
def tree_media(tree_id: int, request: Request, db: Session = Depends(get_db)):
    tree = db.get(TreeVersion, tree_id)
    if not tree or tree.status != "published":
        raise HTTPException(404)
    viewer = read_user(request, db)
    owner = db.get(User, tree.user_id)
    if owner and viewer and is_blocked(db, viewer.id, owner.id):
        raise HTTPException(404)
    return Response(tree.svg_body or "", media_type="image/svg+xml")


@app.get("/api/v1/me/growth-stage")
def my_growth(db: Session = Depends(get_db), user: User = Depends(require_user)):
    return growth_name_only(db, user.id)


# ---------- discovery / friends / dm ----------


@app.get("/api/v1/discovery")
def discovery(db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not sns_ready(user, db):
        raise HTTPException(403, "sns_locked")
    mine = published_leaf_ids(db, user.id)
    blocked = blocked_ids(db, user.id)
    others = db.scalars(select(User).where(User.id != user.id, User.status == "active", User.age_verified_at.is_not(None))).all()
    cards = []
    for other in others:
        if other.id in blocked:
            continue
        theirs = published_leaf_ids(db, other.id)
        if not theirs or not qualifies(mine, theirs):
            continue
        score = similarity(mine, theirs)
        cards.append((score, other))
    cards.sort(key=lambda x: x[0], reverse=True)
    return {
        "items": [
            {**public_profile(db, other, user), "resonance": resonance_label(score)}
            for score, other in cards[:30]
        ]
    }


@app.post("/api/v1/connections")
def connect(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    rate_limit(f"conn:{user.id}", 20)
    if not sns_ready(user, db):
        raise HTTPException(403, "sns_locked")
    body = _json(request)
    receiver_id = int(body.get("user_id"))
    if receiver_id == user.id or is_blocked(db, user.id, receiver_id):
        return error("forbidden", 403)
    other = db.get(User, receiver_id)
    if not other or not sns_ready(other, db):
        return error("not_found", 404)
    if are_friends(db, user.id, receiver_id):
        return error("already_friends", 409)
    existing = db.scalar(
        select(ConnectionRequest).where(
            ConnectionRequest.sender_id == user.id,
            ConnectionRequest.receiver_id == receiver_id,
            ConnectionRequest.status == "pending",
        )
    )
    if existing:
        return {"id": existing.id, "status": "pending"}
    row = ConnectionRequest(
        sender_id=user.id,
        receiver_id=receiver_id,
        message=normalize_text(body.get("message") or "", 200),
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "status": "pending"}


@app.patch("/api/v1/connections/{cid}")
def patch_connection(cid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    row = db.get(ConnectionRequest, cid)
    if not row:
        raise HTTPException(404)
    action = _json(request).get("action")
    if action == "cancel" and row.sender_id == user.id and row.status == "pending":
        row.status = "cancelled"
        row.decided_at = utcnow()
    elif action in {"accept", "decline"} and row.receiver_id == user.id and row.status == "pending":
        row.status = "accepted" if action == "accept" else "declined"
        row.decided_at = utcnow()
        if action == "accept":
            lo, hi = sorted((row.sender_id, row.receiver_id))
            if not are_friends(db, lo, hi):
                db.add(Friendship(user_low_id=lo, user_high_id=hi))
    else:
        return error("forbidden", 403)
    db.commit()
    return {"ok": True, "status": row.status}


@app.get("/api/v1/friends")
def friends(db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not sns_ready(user, db):
        raise HTTPException(403, "sns_locked")
    blocked = blocked_ids(db, user.id)
    rows = db.scalars(
        select(Friendship).where(or_(Friendship.user_low_id == user.id, Friendship.user_high_id == user.id))
    ).all()
    people = []
    for row in rows:
        oid = row.user_high_id if row.user_low_id == user.id else row.user_low_id
        if oid in blocked:
            continue
        other = db.get(User, oid)
        if other:
            people.append(public_profile(db, other, user, for_friend=True))
    incoming = db.scalars(
        select(ConnectionRequest).where(ConnectionRequest.receiver_id == user.id, ConnectionRequest.status == "pending")
    ).all()
    outgoing = db.scalars(
        select(ConnectionRequest).where(ConnectionRequest.sender_id == user.id, ConnectionRequest.status == "pending")
    ).all()
    return {
        "friends": people,
        "incoming": [
            {"id": r.id, "from": public_profile(db, db.get(User, r.sender_id), user), "message": r.message}
            for r in incoming
            if r.sender_id not in blocked
        ],
        "outgoing": [
            {"id": r.id, "to": public_profile(db, db.get(User, r.receiver_id), user), "message": r.message}
            for r in outgoing
        ],
    }


@app.delete("/api/v1/friends/{other_id}")
def unfriend(other_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    lo, hi = sorted((user.id, other_id))
    row = db.scalar(select(Friendship).where(Friendship.user_low_id == lo, Friendship.user_high_id == hi))
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}


def _thread_for(db: Session, a: int, b: int) -> Thread:
    mine = db.scalars(select(ThreadMember.thread_id).where(ThreadMember.user_id == a)).all()
    theirs = set(db.scalars(select(ThreadMember.thread_id).where(ThreadMember.user_id == b)).all())
    shared = [t for t in mine if t in theirs]
    if shared:
        return db.get(Thread, shared[0])
    thread = Thread()
    db.add(thread)
    db.flush()
    db.add(ThreadMember(thread_id=thread.id, user_id=a))
    db.add(ThreadMember(thread_id=thread.id, user_id=b))
    return thread


@app.get("/api/v1/messages/{other_id}")
def list_messages(other_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not are_friends(db, user.id, other_id) or is_blocked(db, user.id, other_id):
        raise HTTPException(403, "forbidden")
    thread = _thread_for(db, user.id, other_id)
    db.commit()
    msgs = db.scalars(select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)).all()
    return {
        "thread_id": thread.id,
        "items": [{"id": m.id, "sender_id": m.sender_id, "body": m.body, "created_at": m.created_at.isoformat()} for m in msgs],
    }


@app.post("/api/v1/messages/{other_id}")
def send_message(other_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    rate_limit(f"dm:{user.id}", 40)
    if not are_friends(db, user.id, other_id) or is_blocked(db, user.id, other_id):
        raise HTTPException(403, "forbidden")
    body = normalize_text(_json(request).get("body") or "", 2000)
    if not body:
        return error("empty", 422)
    crisis = crisis_in(body)
    thread = _thread_for(db, user.id, other_id)
    db.add(Message(thread_id=thread.id, sender_id=user.id, body=body))
    db.commit()
    return {"ok": True, "helpline": PUBLIC_HELPLINES if crisis else None}


# ---------- timelines ----------


def _assert_leaf_access(db: Session, user: User, leaf_id: str):
    if leaf_id not in published_leaf_ids(db, user.id):
        raise HTTPException(403, "leaf_not_selected")
    leaf_map = get_leaf_map(db)
    leaf = leaf_map.get(leaf_id)
    if not leaf or not leaf.timeline_enabled:
        raise HTTPException(403, "timeline_disabled")


def _assert_route_access(db: Session, user: User, origin_id: int):
    route = db.get(CustomRoute, origin_id)
    if not route or route.status != "published":
        raise HTTPException(403, "route_unavailable")
    if origin_id not in adopted_route_ids(db, user.id) and route.creator_id != user.id:
        raise HTTPException(403, "leaf_not_selected")


@app.get("/api/v1/timelines")
def timelines(db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not sns_ready(user, db):
        raise HTTPException(403, "sns_locked")
    ids = sorted(published_leaf_ids(db, user.id))
    leaves = get_leaf_map(db)
    tabs = [
        {"leaf_id": lid, "label_short_ja": leaves[lid].label_short_ja, "type": "leaf"}
        for lid in ids
        if lid in leaves and leaves[lid].timeline_enabled
    ]
    for origin_id in adopted_route_ids(db, user.id):
        route = db.get(CustomRoute, origin_id)
        if route and route.status == "published":
            tabs.append({"origin_route_id": route.id, "label_short_ja": route.leaf_text, "type": "custom"})
    return {"tabs": tabs}


def _serialize_post(db: Session, post: Post, viewer: User) -> dict:
    images = db.scalars(select(PostImage).where(PostImage.post_id == post.id)).all()
    comments = db.scalars(
        select(Comment).where(Comment.post_id == post.id, Comment.status == "visible").order_by(Comment.created_at)
    ).all()
    author = db.get(User, post.user_id)
    mine = db.scalar(
        select(Reaction).where(
            Reaction.actor_id == viewer.id,
            Reaction.target_type == "post",
            Reaction.target_id == str(post.id),
            Reaction.active.is_(True),
        )
    )
    return {
        "id": post.id,
        "author": public_profile(db, author, viewer) if author else None,
        "body": post.body,
        "created_at": post.created_at.isoformat(),
        "images": [{"id": im.id, "thumb_url": f"/api/v1/media/img/{im.thumb_key}", "url": f"/api/v1/media/img/{im.storage_key}"} for im in images],
        "comments": [
            {
                "id": c.id,
                "author": public_profile(db, db.get(User, c.user_id), viewer),
                "body": c.body,
                "created_at": c.created_at.isoformat(),
            }
            for c in comments
        ],
        "reacted": bool(mine),
        "can_react": author.id != viewer.id if author else False,
    }


@app.get("/api/v1/timelines/{leaf_id}/posts")
def leaf_posts(leaf_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not sns_ready(user, db):
        raise HTTPException(403, "sns_locked")
    _assert_leaf_access(db, user, leaf_id)
    blocked = blocked_ids(db, user.id)
    posts = db.scalars(
        select(Post)
        .where(Post.leaf_id == leaf_id, Post.status == "visible")
        .order_by(Post.created_at.desc())
        .limit(50)
    ).all()
    return {"items": [_serialize_post(db, p, user) for p in posts if p.user_id not in blocked]}


@app.post("/api/v1/timelines/{leaf_id}/posts")
async def create_post(
    leaf_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    check_csrf(request)
    rate_limit(f"post:{user.id}", 20)
    if not sns_ready(user, db):
        raise HTTPException(403, "sns_locked")
    _assert_leaf_access(db, user, leaf_id)
    form = await request.form()
    body = normalize_text(str(form.get("body") or ""), 2000)
    if len(body) < 1:
        return error("empty", 422)
    post = Post(user_id=user.id, leaf_id=leaf_id, body=body)
    db.add(post)
    db.flush()
    files = form.getlist("images")
    if len(files) > 4:
        return error("too_many_images", 422)
    for f in files:
        if not hasattr(f, "read"):
            continue
        data = await f.read()
        if not data:
            continue
        try:
            full, thumb, mime, w, h = save_image(data, f.content_type or "")
        except ImageRejected as exc:
            return error(str(exc), 422)
        db.add(PostImage(post_id=post.id, storage_key=full, thumb_key=thumb, mime=mime, width=w, height=h))
    db.commit()
    return {"id": post.id, "helpline": PUBLIC_HELPLINES if crisis_in(body) else None}


@app.get("/api/v1/custom-timelines/{origin_id}/posts")
def custom_posts(origin_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not sns_ready(user, db):
        raise HTTPException(403, "sns_locked")
    _assert_route_access(db, user, origin_id)
    blocked = blocked_ids(db, user.id)
    posts = db.scalars(
        select(Post).where(Post.origin_route_id == origin_id, Post.status == "visible").order_by(Post.created_at.desc()).limit(50)
    ).all()
    return {"items": [_serialize_post(db, p, user) for p in posts if p.user_id not in blocked]}


@app.post("/api/v1/custom-timelines/{origin_id}/posts")
async def create_custom_post(origin_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    if not sns_ready(user, db):
        raise HTTPException(403, "sns_locked")
    _assert_route_access(db, user, origin_id)
    form = await request.form()
    body = normalize_text(str(form.get("body") or ""), 2000)
    if len(body) < 1:
        return error("empty", 422)
    post = Post(user_id=user.id, origin_route_id=origin_id, body=body)
    db.add(post)
    db.commit()
    return {"id": post.id, "helpline": PUBLIC_HELPLINES if crisis_in(body) else None}


@app.post("/api/v1/posts/{pid}/comments")
def add_comment(pid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    rate_limit(f"cmt:{user.id}", 40)
    post = db.get(Post, pid)
    if not post or post.status != "visible":
        raise HTTPException(404)
    if post.leaf_id:
        _assert_leaf_access(db, user, post.leaf_id)
    elif post.origin_route_id:
        _assert_route_access(db, user, post.origin_route_id)
    if is_blocked(db, user.id, post.user_id):
        raise HTTPException(403)
    body = normalize_text(_json(request).get("body") or "", 1000)
    if not body:
        return error("empty", 422)
    db.add(Comment(post_id=pid, user_id=user.id, body=body))
    db.commit()
    return {"ok": True, "helpline": PUBLIC_HELPLINES if crisis_in(body) else None}


# ---------- custom routes ----------


@app.post("/api/v1/custom-routes")
def create_route(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    if not sns_ready(user, db):
        raise HTTPException(403, "sns_locked")
    body = _json(request)
    trunk = normalize_text(body.get("trunk_text") or "", 40)
    branch = normalize_text(body.get("branch_text") or "", 60)
    leaf = normalize_text(body.get("leaf_text") or "", 120)
    if not trunk or not branch or not leaf:
        return error("required", 422)
    similar = []
    published = db.scalars(select(CustomRoute).where(CustomRoute.status == "published")).all()
    for route in published:
        if route.leaf_text == leaf or (route.trunk_text == trunk and route.branch_text == branch):
            similar.append(
                {"id": route.id, "trunk_text": route.trunk_text, "branch_text": route.branch_text, "leaf_text": route.leaf_text}
            )
    status, reason = inspect_custom_route(trunk, branch, leaf)
    route = CustomRoute(
        creator_id=user.id,
        trunk_text=trunk,
        branch_text=branch,
        leaf_text=leaf,
        status=status,
        moderation_reason=reason,
        published_at=utcnow() if status == "published" else None,
    )
    db.add(route)
    db.flush()
    db.add(RouteAdoption(user_id=user.id, origin_route_id=route.id))
    db.commit()
    return {"id": route.id, "status": status, "reason": reason, "similar": similar[:8]}


@app.get("/api/v1/custom-routes/search")
def search_routes(q: str = "", db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not sns_ready(user, db):
        raise HTTPException(403, "sns_locked")
    qn = normalize_text(q, 40)
    rows = db.scalars(select(CustomRoute).where(CustomRoute.status == "published").order_by(CustomRoute.created_at.desc()).limit(40)).all()
    items = []
    mine = adopted_route_ids(db, user.id)
    for route in rows:
        blob = route.trunk_text + route.branch_text + route.leaf_text
        if qn and qn not in blob:
            continue
        reacted = db.scalar(
            select(Reaction).where(
                Reaction.actor_id == user.id,
                Reaction.target_type == "custom_route",
                Reaction.target_id == str(route.id),
                Reaction.active.is_(True),
            )
        )
        items.append(
            {
                "id": route.id,
                "trunk_text": route.trunk_text,
                "branch_text": route.branch_text,
                "leaf_text": route.leaf_text,
                "adopted": route.id in mine,
                "is_owner": route.creator_id == user.id,
                "reacted": bool(reacted),
                "can_react": route.creator_id != user.id,
            }
        )
    return {"items": items}


@app.get("/api/v1/me/custom-routes")
def my_routes(db: Session = Depends(get_db), user: User = Depends(require_user)):
    created = db.scalars(select(CustomRoute).where(CustomRoute.creator_id == user.id)).all()
    return {
        "items": [
            {
                "id": r.id,
                "trunk_text": r.trunk_text,
                "branch_text": r.branch_text,
                "leaf_text": r.leaf_text,
                "status": r.status,
                "reason": r.moderation_reason,
            }
            for r in created
        ]
    }


@app.post("/api/v1/custom-routes/{rid}/adopt")
def adopt_route(rid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    if not sns_ready(user, db):
        raise HTTPException(403, "sns_locked")
    route = db.get(CustomRoute, rid)
    if not route or route.status != "published":
        raise HTTPException(404)
    existing = db.scalar(select(RouteAdoption).where(RouteAdoption.user_id == user.id, RouteAdoption.origin_route_id == rid))
    if existing:
        existing.active = True
        existing.personal_note = normalize_text(_json(request).get("personal_note") or existing.personal_note, 400)
    else:
        db.add(
            RouteAdoption(
                user_id=user.id,
                origin_route_id=rid,
                personal_note=normalize_text(_json(request).get("personal_note") or "", 400),
            )
        )
    db.commit()
    return {"ok": True, "origin_route_id": rid}


@app.delete("/api/v1/custom-routes/{rid}/adoption")
def drop_adoption(rid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    row = db.scalar(select(RouteAdoption).where(RouteAdoption.user_id == user.id, RouteAdoption.origin_route_id == rid))
    if row:
        row.active = False
        db.commit()
    return {"ok": True}


# ---------- reactions / decorations ----------


def _reaction_owner(db: Session, target_type: str, target_id: str) -> int | None:
    if target_type == "post":
        post = db.get(Post, int(target_id))
        return post.user_id if post else None
    if target_type == "post_image":
        img = db.get(PostImage, int(target_id))
        if not img:
            return None
        post = db.get(Post, img.post_id)
        return post.user_id if post else None
    if target_type == "custom_route":
        route = db.get(CustomRoute, int(target_id))
        if not route or route.status != "published":
            return None
        return route.creator_id
    if target_type == "tree":
        other = db.get(User, int(target_id))
        _, published = current_versions(db, other.id) if other else (None, None)
        return other.id if published else None
    return None


@app.put("/api/v1/reactions/{target_type}/{target_id}")
def put_reaction(target_type: str, target_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    rate_limit(f"rx:{user.id}", 80)
    if target_type not in {"post", "post_image", "custom_route", "tree"}:
        return error("invalid_target", 422)
    owner = _reaction_owner(db, target_type, target_id)
    if owner is None:
        raise HTTPException(404)
    if owner == user.id:
        return error("self_reaction", 403)
    if is_blocked(db, user.id, owner):
        raise HTTPException(403)
    row = db.scalar(
        select(Reaction).where(
            Reaction.actor_id == user.id, Reaction.target_type == target_type, Reaction.target_id == str(target_id)
        )
    )
    if row:
        row.active = True
    else:
        db.add(Reaction(actor_id=user.id, target_type=target_type, target_id=str(target_id), owner_user_id=owner, active=True))
    db.flush()
    recalc_growth(db, owner)
    db.commit()
    return {"ok": True}


@app.delete("/api/v1/reactions/{target_type}/{target_id}")
def del_reaction(target_type: str, target_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    row = db.scalar(
        select(Reaction).where(
            Reaction.actor_id == user.id, Reaction.target_type == target_type, Reaction.target_id == str(target_id)
        )
    )
    if row:
        row.active = False
        recalc_growth(db, row.owner_user_id)
        db.commit()
    return {"ok": True}


@app.get("/api/v1/me/post-images")
def my_images(db: Session = Depends(get_db), user: User = Depends(require_user)):
    posts = db.scalars(select(Post).where(Post.user_id == user.id, Post.status == "visible")).all()
    items = []
    for post in posts:
        for img in db.scalars(select(PostImage).where(PostImage.post_id == post.id)):
            items.append(
                {
                    "id": img.id,
                    "thumb_url": f"/api/v1/media/img/{img.thumb_key}",
                    "created_at": post.created_at.isoformat(),
                    "caption": post.body[:80],
                    "post_id": post.id,
                    "leaf_id": post.leaf_id,
                    "origin_route_id": post.origin_route_id,
                }
            )
    return {"items": items}


@app.put("/api/v1/me/tree-decorations")
def put_decorations(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    items = _json(request).get("items") or []
    if len(items) > 12:
        return error("too_many", 422)
    existing = db.scalars(select(TreeDecoration).where(TreeDecoration.user_id == user.id)).all()
    for row in existing:
        db.delete(row)
    db.flush()
    for i, item in enumerate(items):
        img = db.get(PostImage, int(item["post_image_id"]))
        if not img:
            continue
        post = db.get(Post, img.post_id)
        if not post or post.user_id != user.id or post.status != "visible":
            continue
        vis = item.get("visibility") or "private"
        if vis not in {"private", "friends", "same_origin_route"}:
            vis = "private"
        scope_type = "leaf" if post.leaf_id else "custom_route"
        scope_id = post.leaf_id or str(post.origin_route_id)
        db.add(
            TreeDecoration(
                user_id=user.id,
                post_image_id=img.id,
                visibility=vis,
                origin_scope_type=scope_type,
                origin_scope_id=scope_id or "",
                sort_order=i,
            )
        )
    db.commit()
    return {"ok": True}


def _can_see_decoration(db: Session, deco: TreeDecoration, owner_id: int, viewer: User | None) -> bool:
    img = db.get(PostImage, deco.post_image_id)
    post = db.get(Post, img.post_id) if img else None
    if not img or not post or post.status != "visible":
        return False
    if viewer and viewer.id == owner_id:
        return True
    if not viewer:
        return False
    if is_blocked(db, viewer.id, owner_id):
        return False
    if deco.visibility == "private":
        return False
    if deco.visibility == "friends":
        return are_friends(db, viewer.id, owner_id)
    if deco.visibility == "same_origin_route":
        if deco.origin_scope_type == "leaf":
            return deco.origin_scope_id in published_leaf_ids(db, viewer.id) and deco.origin_scope_id in published_leaf_ids(db, owner_id)
        try:
            oid = int(deco.origin_scope_id)
        except ValueError:
            return False
        return oid in adopted_route_ids(db, viewer.id) and oid in adopted_route_ids(db, owner_id)
    return False


@app.get("/api/v1/trees/{user_id}/decorations")
def get_decorations(user_id: int, request: Request, db: Session = Depends(get_db)):
    viewer = read_user(request, db)
    owner = db.get(User, user_id)
    if not owner:
        raise HTTPException(404)
    rows = db.scalars(select(TreeDecoration).where(TreeDecoration.user_id == user_id).order_by(TreeDecoration.sort_order)).all()
    items = []
    for deco in rows:
        if not _can_see_decoration(db, deco, user_id, viewer):
            continue
        img = db.get(PostImage, deco.post_image_id)
        post = db.get(Post, img.post_id)
        items.append(
            {
                "id": deco.id,
                "thumb_url": f"/api/v1/media/img/{img.thumb_key}",
                "created_at": post.created_at.isoformat(),
                "caption": post.body[:80],
                "post_id": post.id,
            }
        )
    return {"items": items}


@app.get("/api/v1/media/img/{name}")
def media_img(name: str, request: Request, db: Session = Depends(get_db)):
    path = media_path(name)
    if not path.exists():
        raise HTTPException(404)
    viewer = read_user(request, db)
    img = db.scalar(select(PostImage).where(or_(PostImage.storage_key == name, PostImage.thumb_key == name)))
    if not img:
        raise HTTPException(404)
    post = db.get(Post, img.post_id)
    if not post or post.status != "visible":
        raise HTTPException(404)
    if viewer and is_blocked(db, viewer.id, post.user_id):
        raise HTTPException(404)
    if not viewer:
        raise HTTPException(401)
    # if used as decoration, still require login; timeline already gated by UI
    if post.leaf_id and post.leaf_id not in published_leaf_ids(db, viewer.id) and post.user_id != viewer.id:
        deco = db.scalar(select(TreeDecoration).where(TreeDecoration.post_image_id == img.id))
        if not deco or not _can_see_decoration(db, deco, post.user_id, viewer):
            raise HTTPException(403)
    return FileResponse(path, media_type="image/jpeg")


# ---------- reports / blocks / admin / settings ----------


@app.post("/api/v1/reports")
def create_report(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    body = _json(request)
    reason = body.get("reason") or "other"
    if reason not in {"harassment", "discrimination", "pii", "solicitation", "harm", "medical", "sexual", "other"}:
        reason = "other"
    row = Report(
        reporter_id=user.id,
        target_type=normalize_text(body.get("target_type") or "", 32),
        target_id=str(body.get("target_id") or ""),
        reason=reason,
        detail=normalize_text(body.get("detail") or "", 1000),
        snapshot_json=json.dumps({"at": utcnow().isoformat()}),
    )
    db.add(row)
    db.flush()
    ticket = f"R{row.id:06d}"
    db.commit()
    return {"ticket": ticket, "status": "open"}


@app.post("/api/v1/blocks/{other_id}")
def block_user(other_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    if other_id == user.id:
        return error("forbidden", 403)
    existing = db.scalar(select(Block).where(Block.blocker_id == user.id, Block.blocked_id == other_id))
    if not existing:
        db.add(Block(blocker_id=user.id, blocked_id=other_id))
    lo, hi = sorted((user.id, other_id))
    fr = db.scalar(select(Friendship).where(Friendship.user_low_id == lo, Friendship.user_high_id == hi))
    if fr:
        db.delete(fr)
    db.commit()
    return {"ok": True}


@app.delete("/api/v1/blocks/{other_id}")
def unblock(other_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    row = db.scalar(select(Block).where(Block.blocker_id == user.id, Block.blocked_id == other_id))
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}


@app.get("/api/v1/admin/reports")
def admin_reports(db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not user.is_admin:
        raise HTTPException(403)
    rows = db.scalars(select(Report).order_by(Report.created_at.desc()).limit(100)).all()
    return {
        "items": [
            {
                "id": r.id,
                "ticket": f"R{r.id:06d}",
                "target_type": r.target_type,
                "target_id": r.target_id,
                "reason": r.reason,
                "detail": r.detail,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
                "snapshot": json.loads(r.snapshot_json or "{}"),
            }
            for r in rows
        ]
    }


@app.post("/api/v1/admin/reports/{rid}/actions")
def admin_action(rid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    if not user.is_admin:
        raise HTTPException(403)
    report = db.get(Report, rid)
    if not report:
        raise HTTPException(404)
    body = _json(request)
    action = body.get("action") or "hide"
    note = normalize_text(body.get("note") or "", 500)
    db.add(ModerationAction(report_id=rid, admin_id=user.id, action=action, note=note))
    report.status = "resolved"
    if action == "hide" and report.target_type == "post":
        post = db.get(Post, int(report.target_id))
        if post:
            post.status = "hidden"
    if action == "suspend" and report.target_type in {"profile", "user"}:
        target = db.get(User, int(report.target_id))
        if target:
            target.status = "suspended"
    audit(db, user.id, action, report.target_type, report.target_id, {"report_id": rid})
    db.commit()
    return {"ok": True}


@app.get("/api/v1/admin/audit")
def admin_audit(db: Session = Depends(get_db), user: User = Depends(require_user)):
    if not user.is_admin:
        raise HTTPException(403)
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)).all()
    return {
        "items": [
            {
                "id": r.id,
                "actor_id": r.actor_id,
                "action": r.action,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@app.get("/api/v1/me/export")
def export_me(db: Session = Depends(get_db), user: User = Depends(require_user)):
    draft, published = current_versions(db, user.id)
    return {
        "user": {"id": user.id, "email": user.email, "created_at": user.created_at.isoformat()},
        "profile": {
            "display_name": user.profile.display_name if user.profile else "",
            "blurb": user.profile.blurb if user.profile else "",
        },
        "leaf_ids": leaf_ids_of(db, published.id) if published else [],
        "posts": [
            {"id": p.id, "body": p.body, "created_at": p.created_at.isoformat()}
            for p in db.scalars(select(Post).where(Post.user_id == user.id)).all()
        ],
    }


@app.delete("/api/v1/posts/{pid}")
def delete_post(pid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    post = db.get(Post, pid)
    if not post or post.user_id != user.id:
        raise HTTPException(404)
    post.status = "deleted"
    db.commit()
    return {"ok": True}


@app.post("/api/v1/me/delete")
def delete_account(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    check_csrf(request)
    user.status = "deleted"
    user.email = f"deleted-{user.id}@invalid.local"
    if user.profile:
        user.profile.display_name = "退会した人"
        user.profile.blurb = ""
    db.commit()
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE)
    resp.delete_cookie(CSRF_COOKIE)
    return resp


@app.post("/api/v1/analytics")
def analytics(request: Request):
    body = _json(request)
    allowed = {k: body.get(k) for k in ("step", "count", "elapsed_ms", "exit") if k in body}
    log.info(json.dumps({"analytics": True, **allowed}))
    return {"ok": True}


def _json(request: Request) -> dict:
    data = JSON_BODY.get()
    if data:
        return data
    try:
        return getattr(request.state, "_json", None) or {}
    except Exception:
        return {}


@app.middleware("http")
async def load_json(request: Request, call_next):
    data: dict = {}
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            parsed = await request.json()
            data = parsed if isinstance(parsed, dict) else {}
        except Exception:
            data = {}
    token = JSON_BODY.set(data)
    try:
        request.state._json = data
        return await call_next(request)
    finally:
        JSON_BODY.reset(token)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
