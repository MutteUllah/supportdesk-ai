import hashlib
import secrets
import time
from collections import defaultdict

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select

from .config import settings
from .db import get_db
from .models import Membership, Session, WidgetSession, now

passwords = PasswordHasher()
dummy_hash = passwords.hash("timing-equalizer-not-an-account")
memory_limits: dict = defaultdict(int)


def digest(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password(encoded, password):
    try:
        return passwords.verify(encoded, password)
    except VerificationError:
        return False


def rate_limit(key: str, limit: int, seconds: int = 60):
    key = "sd:rate:" + digest(key) + ":" + str(int(time.time()) // seconds)
    if settings().test_memory_rate_limit:
        memory_limits[key] += 1
        count = memory_limits[key]
    else:
        try:
            r = Redis.from_url(settings().redis_url, socket_timeout=2, socket_connect_timeout=2)
            count = r.eval(
                "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
                1,
                key,
                seconds,
            )
        except RedisError:
            raise HTTPException(503, "Rate limiter unavailable. Please retry shortly.") from None
    if count > limit:
        raise HTTPException(429, "Too many requests. Please wait before retrying.")


def authenticated(request: Request, db=Depends(get_db)):
    token = request.cookies.get("sd_session", "")
    session = db.scalar(
        select(Session).where(Session.token_hash == digest(token), Session.expires_at > now())
    )
    if not session:
        raise HTTPException(401, "Please log in.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") != settings().dashboard_origin:
            raise HTTPException(403, "Invalid request origin.")
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf):
            raise HTTPException(403, "Invalid CSRF token. Refresh and try again.")
    return session


def member(db, workspace_id, user_id, roles=None):
    membership = db.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id, Membership.user_id == user_id
        )
    )
    if not membership:
        raise HTTPException(404, "Workspace not found.")
    if roles and membership.role not in roles:
        raise HTTPException(403, "Your role cannot perform this action.")
    return membership


def visitor(request: Request, db=Depends(get_db)):
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    session = db.scalar(
        select(WidgetSession).where(
            WidgetSession.token_hash == digest(token), WidgetSession.expires_at > now()
        )
    )
    if not session:
        raise HTTPException(401, "Visitor session expired. Start a new conversation.")
    rate_limit("visitor:" + session.id, 90)
    return session
