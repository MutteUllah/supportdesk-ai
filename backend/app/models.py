"""Tenant keys are repeated in composite foreign keys: isolation is also a DB invariant."""

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class Tenant(Record):
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )


class User(Record, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)


class Session(Record, Base):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class Workspace(Record, Base):
    __tablename__ = "workspaces"
    name: Mapped[str] = mapped_column(String(100))
    public_id: Mapped[str] = mapped_column(String(36), unique=True, default=uid)
    bot_name: Mapped[str] = mapped_column(String(100), default="Support assistant")
    welcome: Mapped[str] = mapped_column(String(500), default="Hello! How can we help?")
    color: Mapped[str] = mapped_column(String(7), default="#166c60")
    origins: Mapped[list] = mapped_column(JSON, default=list)
    embedding_identity: Mapped[str] = mapped_column(String(200))
    quota_day: Mapped[str] = mapped_column(String(10), default="")
    quota_used: Mapped[int] = mapped_column(Integer, default=0)
    quota_limit: Mapped[int] = mapped_column(Integer, default=1000)


class Membership(Tenant, Base):
    __tablename__ = "memberships"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id"),
        CheckConstraint("role in ('owner','administrator','support-agent')"),
    )


class WidgetSession(Tenant, Base):
    __tablename__ = "widget_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    origin: Mapped[str] = mapped_column(String(300))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    __table_args__ = (UniqueConstraint("workspace_id", "id"),)


class Document(Tenant, Base):
    __tablename__ = "documents"
    name: Mapped[str] = mapped_column(String(200))
    active_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("workspace_id", "id"),)


class DocumentVersion(Tenant, Base):
    __tablename__ = "document_versions"
    document_id: Mapped[str] = mapped_column(String(36))
    number: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    embedding_identity: Mapped[str] = mapped_column(String(200))
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("document_id", "number"),
        ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["documents.workspace_id", "documents.id"],
            ondelete="CASCADE",
        ),
    )


class DocumentChunk(Tenant, Base):
    __tablename__ = "document_chunks"
    version_id: Mapped[str] = mapped_column(String(36))
    ordinal: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(Vector().with_variant(JSON, "sqlite"))
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("version_id", "ordinal"),
        ForeignKeyConstraint(
            ["workspace_id", "version_id"],
            ["document_versions.workspace_id", "document_versions.id"],
            ondelete="CASCADE",
        ),
    )


class Conversation(Tenant, Base):
    __tablename__ = "conversations"
    visitor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    state: Mapped[str] = mapped_column(String(20), default="bot")
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "visitor_id"],
            ["widget_sessions.workspace_id", "widget_sessions.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("state in ('bot','pending-human','human')"),
    )


class Message(Tenant, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[str] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    request_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="complete")
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("conversation_id", "request_key", "role"),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        Index("message_history", "conversation_id", "created_at"),
    )


class MessageCitation(Tenant, Base):
    __tablename__ = "message_citations"
    message_id: Mapped[str] = mapped_column(String(36))
    document_id: Mapped[str] = mapped_column(String(36))
    version_id: Mapped[str] = mapped_column(String(36))
    chunk_id: Mapped[str] = mapped_column(String(36))
    page: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(200))
    excerpt: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "message_id"],
            ["messages.workspace_id", "messages.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["documents.workspace_id", "documents.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "version_id"],
            ["document_versions.workspace_id", "document_versions.id"],
            ondelete="CASCADE",
        ),
    )


class Ticket(Tenant, Base):
    __tablename__ = "tickets"
    conversation_id: Mapped[str] = mapped_column(String(36))
    action_key: Mapped[str] = mapped_column(String(80))
    subject: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    assignee_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("conversation_id", "action_key"),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("status in ('open','in progress','resolved')"),
    )


class ToolExecution(Tenant, Base):
    __tablename__ = "tool_executions"
    conversation_id: Mapped[str] = mapped_column(String(36))
    action_key: Mapped[str] = mapped_column(String(80))
    ticket_id: Mapped[str] = mapped_column(String(36))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("conversation_id", "action_key"),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "ticket_id"],
            ["tickets.workspace_id", "tickets.id"],
            ondelete="CASCADE",
        ),
    )


class UsageEvent(Tenant, Base):
    __tablename__ = "usage_events"
    model: Mapped[str] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0)
