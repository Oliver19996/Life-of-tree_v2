from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session

from .config import DATABASE_URL, DATA_DIR, UPLOAD_DIR


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    google_sub: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    age_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    terms_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reaction_notify: Mapped[str] = mapped_column(String(16), default="digest")  # on / digest / off

    profile: Mapped[Optional["Profile"]] = relationship(back_populates="user", uselist=False)


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(40), default="")
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    blurb: Mapped[str] = mapped_column(String(400), default="")
    blurb_visibility: Mapped[str] = mapped_column(String(16), default="friends")  # public / friends / hidden

    user: Mapped[User] = relationship(back_populates="profile")


class TaxonomyTrunk(Base):
    __tablename__ = "taxonomy_trunks"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    label_ja: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TaxonomyBranch(Base):
    __tablename__ = "taxonomy_branches"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    trunk_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_trunks.id"))
    label_ja: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TaxonomyLeaf(Base):
    __tablename__ = "taxonomy_leaves"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    branch_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_branches.id"))
    label_ja: Mapped[str] = mapped_column(String(200))  # description_ja kept here per spec mapping
    label_short_ja: Mapped[str] = mapped_column(String(40))
    description_ja: Mapped[str] = mapped_column(String(400))
    search_terms_ja: Mapped[str] = mapped_column(Text, default="[]")
    sensitivity: Mapped[str] = mapped_column(String(16), default="normal")
    timeline_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    visual_seed: Mapped[str] = mapped_column(String(64))
    visual_tags_json: Mapped[str] = mapped_column(Text, default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TreeVersion(Base):
    __tablename__ = "tree_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft / published
    svg_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    svg_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class TreeSelection(Base):
    __tablename__ = "tree_selections"
    __table_args__ = (UniqueConstraint("tree_version_id", "leaf_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tree_version_id: Mapped[int] = mapped_column(ForeignKey("tree_versions.id"), index=True)
    leaf_id: Mapped[str] = mapped_column(ForeignKey("taxonomy_leaves.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomRoute(Base):
    __tablename__ = "custom_routes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    trunk_text: Mapped[str] = mapped_column(String(40))
    branch_text: Mapped[str] = mapped_column(String(60))
    leaf_text: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="draft")
    moderation_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    moderation_model: Mapped[str] = mapped_column(String(32), default="rules-v1")
    origin_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class RouteAdoption(Base):
    __tablename__ = "route_adoptions"
    __table_args__ = (UniqueConstraint("user_id", "origin_route_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    origin_route_id: Mapped[int] = mapped_column(ForeignKey("custom_routes.id"), index=True)
    personal_note: Mapped[str] = mapped_column(String(400), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    leaf_id: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    origin_route_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="visible")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PostImage(Base):
    __tablename__ = "post_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    thumb_key: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(64))
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    scan_status: Mapped[str] = mapped_column(String(16), default="ok")


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="visible")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConnectionRequest(Base):
    __tablename__ = "connection_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    receiver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Friendship(Base):
    __tablename__ = "friendships"
    __table_args__ = (UniqueConstraint("user_low_id", "user_high_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_low_id: Mapped[int] = mapped_column(Integer, index=True)
    user_high_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Thread(Base):
    __tablename__ = "threads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ThreadMember(Base):
    __tablename__ = "thread_members"
    __table_args__ = (UniqueConstraint("thread_id", "user_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (UniqueConstraint("actor_id", "target_type", "target_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(24))  # post / post_image / custom_route / tree
    target_id: Mapped[str] = mapped_column(String(64))
    owner_user_id: Mapped[int] = mapped_column(Integer, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GrowthSnapshot(Base):
    __tablename__ = "growth_snapshots"
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    valid_reaction_count: Mapped[int] = mapped_column(Integer, default=0)
    growth_stage: Mapped[int] = mapped_column(Integer, default=1)
    growth_rule_version: Mapped[int] = mapped_column(Integer, default=1)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TreeDecoration(Base):
    __tablename__ = "tree_decorations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    post_image_id: Mapped[int] = mapped_column(ForeignKey("post_images.id"))
    visibility: Mapped[str] = mapped_column(String(32), default="private")
    origin_scope_type: Mapped[str] = mapped_column(String(24), default="leaf")  # leaf / custom_route
    origin_scope_id: Mapped[str] = mapped_column(String(32), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blocker_id: Mapped[int] = mapped_column(Integer, index=True)
    blocked_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModerationAction(Base):
    __tablename__ = "moderation_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MagicLink(Base):
    __tablename__ = "magic_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class AiJob(Base):
    __tablename__ = "ai_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    tree_version_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    provider: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(16), default="v1")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@event.listens_for(engine, "connect")
def _sqlite_pragma(dbapi_connection, _connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    from .catalog import seed_catalog

    db = SessionLocal()
    try:
        seed_catalog(db)
        db.commit()
    finally:
        db.close()
