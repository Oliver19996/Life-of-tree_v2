from __future__ import annotations

import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Annotated
from urllib.parse import urlencode

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from .db import (
    Block,
    ConnectionRequest,
    DATA_DIR,
    Embedding,
    MagicToken,
    Message,
    Profile,
    SessionLocal,
    Thread,
    TreePosition,
    User,
    init_db,
)
from .images import stylize_selfie
from .taxonomy import catalog, compose_role_input, labels
from .vectors import cosine, dumps, embed_text, loads

load_dotenv()

SECRET = os.getenv("APP_SECRET", "dev-secret-change")
BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
ALLOW_DEMO = os.getenv("ALLOW_DEMO_LOGIN", "true").lower() == "true"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
MAX_GENS = 2

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="Tree of Life", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


Db = Annotated[Session, Depends(get_db)]


def set_session(resp, user_id: int):
    from itsdangerous import URLSafeTimedSerializer

    s = URLSafeTimedSerializer(SECRET, salt="tof-session")
    resp.set_cookie(
        "tof",
        s.dumps({"uid": user_id}),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )


def current_user(request: Request, db: Session) -> User | None:
    from itsdangerous import BadSignature, URLSafeTimedSerializer

    raw = request.cookies.get("tof")
    if not raw:
        return None
    try:
        data = URLSafeTimedSerializer(SECRET, salt="tof-session").loads(raw, max_age=60 * 60 * 24 * 30)
    except BadSignature:
        return None
    return db.get(User, data.get("uid"))


def require_user(request: Request, db: Db) -> User:
    user = current_user(request, db)
    if not user:
        raise HTTPException(401, "login required")
    return user


AuthUser = Annotated[User, Depends(require_user)]


def public_user(u: User) -> dict:
    p = u.profile
    pos = u.position
    limb_ja = bough_ja = grain_ja = None
    if pos:
        limb_ja, bough_ja, grain_ja = labels(pos.limb_id, pos.bough_id, pos.grain_id)
    return {
        "id": u.id,
        "display_name": p.display_name if p else "Walker",
        "avatar_url": p.avatar_url if p else "/static/presets/leaf.svg",
        "avatar_kind": p.avatar_kind if p else "preset",
        "city": p.city if p else None,
        "blurb": p.blurb if p else None,
        "onboarding_done": bool(p and p.onboarding_done),
        "plan": u.plan,
        "avatar_gens_used": p.avatar_gens_used if p else 0,
        "avatar_gens_max": MAX_GENS,
        "tree": None
        if not pos
        else {
            "limb_id": pos.limb_id,
            "bough_id": pos.bough_id,
            "grain_id": pos.grain_id,
            "limb": limb_ja,
            "bough": bough_ja,
            "grain": grain_ja,
        },
    }


def upsert_embedding(db: Session, user: User) -> None:
    p, pos = user.profile, user.position
    if not p or not pos:
        return
    text = compose_role_input(p.display_name, pos.limb_id, pos.bough_id, pos.grain_id, p.blurb, p.city)
    vec = embed_text(text, pos.limb_id, pos.bough_id, pos.grain_id)
    row = user.embedding or Embedding(user_id=user.id)
    row.vector = dumps(vec)
    db.add(row)


def ensure_profile(db: Session, user: User) -> Profile:
    if user.profile:
        return user.profile
    p = Profile(user_id=user.id, display_name=user.email.split("@")[0][:40])
    db.add(p)
    db.flush()
    return p


SEED = [
    ("mio@seed.tof", "澪", "care", "b07", "graft", "看取りのあと、同じ夜にいた人へ。", "京都"),
    ("ken@seed.tof", "Ken", "border", "b02", "ring", "就労ビザの楔を打ち終わった側。", "Toronto"),
    ("aya@seed.tof", "彩", "work", "b04", "sap", "まだ燃えている。消さないでほしい。", "東京"),
    ("noah@seed.tof", "Noah", "love", "b06", "greenwood", "別れの手前で、同じ枝を探している。", "London"),
    ("rin@seed.tof", "凛", "mind", "b01", "ring", "初遭遇のあとの年輪。", "大阪"),
    ("sam@seed.tof", "Sam", "make", "b03", "graft", "閉業を一度やった。次の人の楔になる。", "Brooklyn"),
    ("yui@seed.tof", "結", "child", "b03", "sap", "ひとり親の樹液の中。", "福岡"),
    ("leo@seed.tof", "Leo", "belong", "b01", "wedge", "今日、名前を言いに行く。", "Sydney"),
]


def seed_if_empty(db: Session) -> None:
    if db.query(User).count() > 0:
        return
    for email, name, limb, bough, grain, blurb, city in SEED:
        u = User(email=email)
        db.add(u)
        db.flush()
        db.add(
            Profile(
                user_id=u.id,
                display_name=name,
                blurb=blurb,
                city=city,
                onboarding_done=True,
                avatar_url=f"/static/presets/{(u.id % 6) + 1}.svg",
            )
        )
        db.add(TreePosition(user_id=u.id, limb_id=limb, bough_id=bough, grain_id=grain))
        db.flush()
        u = db.get(User, u.id)
        upsert_embedding(db, u)
    db.commit()


@app.on_event("startup")
def startup():
    init_db()
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"ok": True, "name": "Tree of Life"}


@app.get("/api/catalog")
def api_catalog():
    return catalog()


@app.get("/api/me")
def me(request: Request, db: Db):
    user = current_user(request, db)
    if not user:
        return {"user": None, "google": bool(GOOGLE_CLIENT_ID), "demo": ALLOW_DEMO}
    return {"user": public_user(user), "google": bool(GOOGLE_CLIENT_ID), "demo": ALLOW_DEMO}


class MagicIn(BaseModel):
    email: EmailStr


def send_magic(email: str, url: str) -> None:
    host = os.getenv("SMTP_HOST")
    if not host:
        print(f"[TOF magic] {email} {url}")
        return
    msg = EmailMessage()
    msg["Subject"] = "Tree of Life — enter the grove"
    msg["From"] = os.getenv("SMTP_FROM", "noreply@treeoflife.local")
    msg["To"] = email
    msg.set_content(f"森に入るリンク（30分）:\n{url}\n")
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as s:
        s.starttls()
        if os.getenv("SMTP_USER"):
            s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
        s.send_message(msg)


@app.post("/api/auth/magic")
def auth_magic(body: MagicIn, db: Db):
    token = secrets.token_urlsafe(24)
    db.add(MagicToken(token=token, email=body.email.lower()))
    db.commit()
    url = f"{BASE_URL}/api/auth/magic/callback?token={token}"
    send_magic(body.email.lower(), url)
    payload = {"ok": True, "message": "リンクを送りました。メール設定がない場合は下のリンクで入れます。"}
    if not os.getenv("SMTP_HOST"):
        payload["dev_link"] = url
    return payload


@app.get("/api/auth/magic/callback")
def magic_cb(token: str, db: Db):
    row = db.get(MagicToken, token)
    if not row:
        raise HTTPException(400, "invalid link")
    if datetime.utcnow() - row.created_at > timedelta(minutes=30):
        db.delete(row)
        db.commit()
        raise HTTPException(400, "expired")
    email = row.email
    db.delete(row)
    user = db.query(User).filter_by(email=email).one_or_none()
    if not user:
        user = User(email=email)
        db.add(user)
        db.flush()
        ensure_profile(db, user)
    db.commit()
    resp = RedirectResponse("/", status_code=302)
    set_session(resp, user.id)
    return resp


@app.post("/api/auth/demo")
def auth_demo(db: Db):
    if not ALLOW_DEMO:
        raise HTTPException(403, "demo off")
    email = f"demo-{secrets.token_hex(6)}@grove.tof"
    user = User(email=email)
    db.add(user)
    db.flush()
    ensure_profile(db, user)
    db.commit()
    resp = JSONResponse({"ok": True, "user": public_user(user)})
    set_session(resp, user.id)
    return resp


@app.get("/api/auth/google")
def google_start():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(400, "Google is not configured")
    qs = urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": f"{BASE_URL}/api/auth/google/callback",
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "online",
        }
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{qs}")


@app.get("/api/auth/google/callback")
async def google_cb(code: str, db: Db):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(400, "Google is not configured")
    import httpx

    async with httpx.AsyncClient() as client:
        token = (
            await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": f"{BASE_URL}/api/auth/google/callback",
                    "grant_type": "authorization_code",
                },
            )
        ).json()
        if "access_token" not in token:
            raise HTTPException(400, "google token failed")
        info = (
            await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {token['access_token']}"},
            )
        ).json()
    email = (info.get("email") or "").lower()
    sub = info.get("sub")
    if not email:
        raise HTTPException(400, "no email")
    user = db.query(User).filter_by(email=email).one_or_none()
    if not user:
        user = User(email=email, google_sub=sub)
        db.add(user)
        db.flush()
        p = ensure_profile(db, user)
        if info.get("name"):
            p.display_name = info["name"][:40]
    else:
        user.google_sub = sub
    db.commit()
    resp = RedirectResponse("/", status_code=302)
    set_session(resp, user.id)
    return resp


@app.post("/api/auth/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("tof")
    return resp


class ProfileIn(BaseModel):
    display_name: str | None = None
    city: str | None = None
    blurb: str | None = None
    limb_id: str | None = None
    bough_id: str | None = None
    grain_id: str | None = None
    avatar_kind: str | None = None
    avatar_url: str | None = None


@app.post("/api/onboarding")
def onboarding(body: ProfileIn, user: AuthUser, db: Db):
    p = ensure_profile(db, user)
    if body.display_name:
        p.display_name = body.display_name.strip()[:40]
    p.city = (body.city or "").strip()[:40] or None
    p.blurb = (body.blurb or "").strip()[:140] or None
    if body.avatar_kind in {"preset", "upload", "generated"}:
        p.avatar_kind = body.avatar_kind
    if body.avatar_url:
        p.avatar_url = body.avatar_url[:400]
    if body.limb_id and body.bough_id and body.grain_id:
        pos = user.position or TreePosition(user_id=user.id)
        pos.limb_id = body.limb_id
        pos.bough_id = body.bough_id
        pos.grain_id = body.grain_id
        db.add(pos)
        p.onboarding_done = True
    db.flush()
    upsert_embedding(db, user)
    db.commit()
    db.refresh(user)
    return {"user": public_user(user)}


@app.post("/api/avatar/upload")
async def avatar_upload(user: AuthUser, db: Db, file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 6_000_000:
        raise HTTPException(400, "file too large")
    ext = "jpg"
    path = os.path.join(DATA_DIR, "uploads", f"u{user.id}.{ext}")
    with open(path, "wb") as f:
        f.write(data)
    p = ensure_profile(db, user)
    p.avatar_kind = "upload"
    p.avatar_url = f"/media/uploads/u{user.id}.{ext}"
    db.commit()
    return {"url": p.avatar_url}


@app.post("/api/avatar/generate")
async def avatar_generate(user: AuthUser, db: Db, file: UploadFile = File(...)):
    p = ensure_profile(db, user)
    if p.avatar_gens_used >= MAX_GENS:
        raise HTTPException(429, "生成回数の上限です")
    data = await file.read()
    url = stylize_selfie(data, user.id)
    p.avatar_kind = "generated"
    p.avatar_url = url
    p.avatar_gens_used += 1
    db.commit()
    return {"url": url, "used": p.avatar_gens_used, "max": MAX_GENS}


@app.get("/api/discover")
def discover(user: AuthUser, db: Db):
    pos = user.position
    if not pos:
        return {"people": []}
    blocked = {b.target_id for b in db.query(Block).filter_by(actor_id=user.id)}
    q = (
        db.query(User)
        .join(TreePosition, TreePosition.user_id == User.id)
        .join(Profile, Profile.user_id == User.id)
        .filter(TreePosition.limb_id == pos.limb_id, TreePosition.bough_id == pos.bough_id, User.id != user.id)
    )
    people = []
    my_vec = loads(user.embedding.vector) if user.embedding else None
    for other in q.all():
        if other.id in blocked or not other.position:
            continue
        score = 0.0
        if my_vec is not None and other.embedding:
            score = cosine(my_vec, loads(other.embedding.vector))
        item = public_user(other)
        item["score"] = round(score, 4)
        people.append(item)
    people.sort(key=lambda x: -x["score"])
    return {"people": people}


class RequestIn(BaseModel):
    to_id: int
    intro: str = ""


@app.post("/api/requests")
def make_request(body: RequestIn, user: AuthUser, db: Db):
    if body.to_id == user.id:
        raise HTTPException(400, "self")
    existing = (
        db.query(ConnectionRequest)
        .filter_by(from_id=user.id, to_id=body.to_id)
        .filter(ConnectionRequest.status != "declined")
        .one_or_none()
    )
    if existing:
        return {"ok": True, "id": existing.id, "status": existing.status}
    row = ConnectionRequest(from_id=user.id, to_id=body.to_id, intro=body.intro[:80])
    db.add(row)
    db.commit()
    return {"ok": True, "id": row.id, "status": row.status}


@app.get("/api/inbox")
def inbox(user: AuthUser, db: Db):
    incoming = db.query(ConnectionRequest).filter_by(to_id=user.id).all()
    outgoing = db.query(ConnectionRequest).filter_by(from_id=user.id).all()

    def pack(row: ConnectionRequest):
        other_id = row.from_id if row.to_id == user.id else row.to_id
        other = db.get(User, other_id)
        return {
            "id": row.id,
            "status": row.status,
            "intro": row.intro,
            "from_me": row.from_id == user.id,
            "other": public_user(other) if other else None,
        }

    threads = db.query(Thread).filter((Thread.a_id == user.id) | (Thread.b_id == user.id)).all()
    tpack = []
    for t in threads:
        other_id = t.b_id if t.a_id == user.id else t.a_id
        other = db.get(User, other_id)
        last = db.query(Message).filter_by(thread_id=t.id).order_by(Message.id.desc()).first()
        tpack.append(
            {
                "id": t.id,
                "other": public_user(other) if other else None,
                "last": last.body if last else "",
            }
        )
    return {"requests": [pack(r) for r in incoming + outgoing], "threads": tpack}


class DecideIn(BaseModel):
    accept: bool


@app.post("/api/requests/{rid}/decide")
def decide(rid: int, body: DecideIn, user: AuthUser, db: Db):
    row = db.get(ConnectionRequest, rid)
    if not row or row.to_id != user.id:
        raise HTTPException(404)
    row.status = "accepted" if body.accept else "declined"
    if body.accept:
        a, b = sorted([row.from_id, row.to_id])
        t = db.query(Thread).filter_by(a_id=a, b_id=b).one_or_none()
        if not t:
            t = Thread(a_id=a, b_id=b)
            db.add(t)
            db.flush()
            if row.intro:
                db.add(Message(thread_id=t.id, sender_id=row.from_id, body=row.intro))
    db.commit()
    return {"ok": True, "status": row.status}


@app.get("/api/threads/{tid}")
def thread_get(tid: int, user: AuthUser, db: Db):
    t = db.get(Thread, tid)
    if not t or user.id not in {t.a_id, t.b_id}:
        raise HTTPException(404)
    msgs = db.query(Message).filter_by(thread_id=tid).order_by(Message.id.asc()).all()
    other_id = t.b_id if t.a_id == user.id else t.a_id
    return {
        "id": tid,
        "other": public_user(db.get(User, other_id)),
        "messages": [{"id": m.id, "mine": m.sender_id == user.id, "body": m.body} for m in msgs],
    }


class MsgIn(BaseModel):
    body: str


@app.post("/api/threads/{tid}/messages")
def thread_send(tid: int, body: MsgIn, user: AuthUser, db: Db):
    t = db.get(Thread, tid)
    if not t or user.id not in {t.a_id, t.b_id}:
        raise HTTPException(404)
    text = body.body.strip()[:2000]
    if not text:
        raise HTTPException(400, "empty")
    m = Message(thread_id=tid, sender_id=user.id, body=text)
    db.add(m)
    db.commit()
    return {"id": m.id, "mine": True, "body": m.body}


@app.post("/api/block/{uid}")
def block(uid: int, user: AuthUser, db: Db):
    if uid == user.id:
        raise HTTPException(400)
    if not db.query(Block).filter_by(actor_id=user.id, target_id=uid).one_or_none():
        db.add(Block(actor_id=user.id, target_id=uid))
        db.commit()
    return {"ok": True}


@app.get("/media/uploads/{name}")
def media_uploads(name: str):
    path = os.path.join(DATA_DIR, "uploads", name)
    if not os.path.isfile(path):
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/media/avatars/{name}")
def media_avatars(name: str):
    path = os.path.join(DATA_DIR, "avatars", name)
    if not os.path.isfile(path):
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
