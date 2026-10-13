import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def email_valid(cls, v):
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", v):
            raise ValueError("Enter a valid email address")
        return v.lower().strip()


class WorkspaceInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class WorkspaceSettings(WorkspaceInput):
    bot_name: str = Field(min_length=1, max_length=100)
    welcome: str = Field(min_length=1, max_length=500)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    origins: list[str] = Field(max_length=20)

    @field_validator("origins")
    @classmethod
    def valid_origins(cls, values):
        for value in values:
            url = urlsplit(value)
            if (
                url.scheme not in {"https", "http"}
                or not url.hostname
                or url.path
                or url.query
                or url.fragment
                or url.username
            ):
                raise ValueError(
                    "Use exact origins, e.g. https://shop.example.com (no trailing slash)"
                )
            if not re.fullmatch(r"https?://[A-Za-z0-9.\-\[\]:]+", value):
                raise ValueError("Invalid origin")
        return list(dict.fromkeys(values))


class MemberInput(BaseModel):
    email: str = Field(max_length=254)
    role: Literal["administrator", "support-agent"]


class ChatInput(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    request_key: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    action: Literal["chat", "ticket", "handoff"] = "chat"
    consent: bool = False
    subject: str = Field(default="", max_length=200)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Message must not be blank")
        return value.strip()

    @field_validator("email")
    @classmethod
    def optional_email(cls, value):
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email")
        return value or None


class ReplyInput(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class TicketUpdate(BaseModel):
    status: Literal["open", "in progress", "resolved"]
    assignee_id: str | None = None


class VisitorInput(BaseModel):
    origin: str = Field(max_length=300)
