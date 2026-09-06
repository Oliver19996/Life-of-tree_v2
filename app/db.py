from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "uploads"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "avatars"), exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "tof.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    google_sub: Mapped[str | None] = mapped_column(String(128), nullable=True)
    plan: Mapped[str] = mapped_column(String(16), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    profile: Mapped[Profile | None] = relationship(back_populates="user", uselist=False)
    position: Mapped[TreePosition | None] = relationship(back_populates="user", uselist=False)
    embedding: Mapped[Embedding | None] = relationship(back_populates="user", uselist=False)


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(40), default="Walker")
    avatar_kind: Mapped[str] = mapped_column(String(16), default="preset")
    avatar_url: Mapped[str] = mapped_column(String(400), default="/static/presets/leaf.svg")
    city: Mapped[str | None] = mapped_column(String(40), nullable=True)
    blurb: Mapped[str | None] = mapped_column(String(140), nullable=True)
    avatar_gens_used: Mapped[int] = mapped_column(Integer, default=0)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="profile")


class TreePosition(Base):
    __tablename__ = "tree_positions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    limb_id: Mapped[str] = mapped_column(String(32))
    bough_id: Mapped[str] = mapped_column(String(16))
    grain_id: Mapped[str] = mapped_column(String(16))

    user: Mapped[User] = relationship(back_populates="position")


class Embedding(Base):
    __tablename__ = "embeddings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    vector: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(32), default="tof-v1")

    user: Mapped[User] = relationship(back_populates="embedding")


class MagicToken(Base):
    __tablename__ = "magic_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConnectionRequest(Base):
    __tablename__ = "connection_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    to_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    intro: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    a_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    b_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id"))
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Block(Base):
    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    target_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


def init_db() -> None:
    Base.metadata.create_all(engine)
