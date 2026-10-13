import json
import logging
import secrets
import time
from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from . import storage
from .chat import run_chat
from .config import settings
from .db import SessionLocal, get_db
from .ingestion import dispatch
from .limits import BodyLimitMiddleware
from .models import (
    Conversation,
    Document,
    DocumentVersion,
    Membership,
    Message,
    MessageCitation,
    Session,
    Ticket,
    UsageEvent,
    User,
    WidgetSession,
    Workspace,
    now,
    uid,
)
from .provider import ProviderError
from .schemas import (
    ChatInput,
    Credentials,
    MemberInput,
    ReplyInput,
    TicketUpdate,
    VisitorInput,
    WorkspaceInput,
    WorkspaceSettings,
)
from .security import (
    authenticated,
    digest,
    dummy_hash,
    member,
    passwords,
    rate_limit,
    verify_password,
    visitor,
)

app = FastAPI(title="SupportDesk AI", version="1.0.0")
app.add_middleware(BodyLimitMiddleware, max_bytes=settings().max_upload_bytes + 65536)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings().dashboard_origin, settings().api_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
)
log = logging.getLogger("supportdesk")
if not log.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)
log.setLevel(logging.INFO)
log.propagate = False
MANAGERS = {"owner", "administrator"}


@app.middleware("http")
async def request_metadata(request, call_next):
    request.state.request_id = uid()
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        response = JSONResponse(
            status_code=500,
            content={
                "detail": "Unexpected server error. Contact support with the request ID.",
                "request_id": request.state.request_id,
            },
        )
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    log.info(
        json.dumps(
            {
                "request_id": request.state.request_id,
                "method": request.method,
                "status": response.status_code,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        )
    )
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": request.state.request_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Never echo rejected inputs (which can include passwords).
    return JSONResponse(
        status_code=422,
        content={
            "detail": "; ".join(
                f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()
            ),
            "request_id": request.state.request_id,
        },
    )


def row(obj):
    return {
        c.name: (
            getattr(obj, c.name).isoformat()
            if hasattr(getattr(obj, c.name), "isoformat")
            else getattr(obj, c.name)
        )
        for c in obj.__table__.columns
    }


def owned(db, cls, workspace_id, record_id):
    obj = db.scalar(select(cls).where(cls.workspace_id == workspace_id, cls.id == record_id))
    if not obj:
        raise HTTPException(404, "Resource not found.")
    return obj


def workspace_row(w):
    return {k: v for k, v in row(w).items() if k not in {"embedding_identity"}}


def set_session(db, user, response):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    session = Session(
        user_id=user.id,
        token_hash=digest(token),
        csrf=csrf,
        expires_at=now() + timedelta(hours=settings().session_hours),
    )
    db.add(session)
    db.commit()
    response.set_cookie(
        "sd_session",
        token,
        httponly=True,
        secure=settings().environment == "production",
        samesite="lax",
        max_age=settings().session_hours * 3600,
        path="/",
    )
    return {"id": user.id, "email": user.email, "csrf": csrf}


def auth_limit(request):
    if request.headers.get("origin") != settings().dashboard_origin:
        raise HTTPException(403, "Invalid origin.")
    rate_limit("auth:" + (request.client.host if request.client else "unknown"), 20)


@app.post("/auth/register")
def register(payload: Credentials, request: Request, response: Response, db=Depends(get_db)):
    auth_limit(request)
    user = User(email=payload.email, password_hash=passwords.hash(payload.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Unable to register this email. Try logging in.") from None
    return set_session(db, user, response)


@app.post("/auth/login")
def login(payload: Credentials, request: Request, response: Response, db=Depends(get_db)):
    auth_limit(request)
    user = db.scalar(select(User).where(User.email == payload.email))
    if (
        not verify_password(user.password_hash if user else dummy_hash, payload.password)
        or not user
    ):
        raise HTTPException(401, "Invalid email or password.")
    return set_session(db, user, response)


@app.get("/auth/me")
def me(session=Depends(authenticated), db=Depends(get_db)):
    user = db.get(User, session.user_id)
    return {
        "id": user.id,
        "email": user.email,
        "csrf": session.csrf,
        "model_mode": settings().model_mode,
    }


@app.post("/auth/logout")
def logout(response: Response, session=Depends(authenticated), db=Depends(get_db)):
    db.delete(session)
    db.commit()
    response.delete_cookie("sd_session", path="/")
    return {"ok": True}


@app.get("/workspaces")
def workspaces(session=Depends(authenticated), db=Depends(get_db)):
    rows = db.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == session.user_id)
    ).all()
    return [{**workspace_row(w), "role": role} for w, role in rows]


@app.post("/workspaces")
def create_workspace(payload: WorkspaceInput, session=Depends(authenticated), db=Depends(get_db)):
    w = Workspace(
        name=payload.name,
        embedding_identity=settings().embedding_identity,
        quota_limit=settings().daily_chat_quota,
    )
    db.add(w)
    db.flush()
    db.add(Membership(workspace_id=w.id, user_id=session.user_id, role="owner"))
    db.commit()
    return workspace_row(w)


@app.patch("/workspaces/{wid}")
def update_workspace(
    wid: str, payload: WorkspaceSettings, session=Depends(authenticated), db=Depends(get_db)
):
    member(db, wid, session.user_id, {"owner"})
    w = db.get(Workspace, wid)
    for key, value in payload.model_dump().items():
        setattr(w, key, value)
    db.commit()
    return workspace_row(w)


@app.get("/workspaces/{wid}/overview")
def overview(wid: str, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id)
    w = db.get(Workspace, wid)
    counts = {
        "conversations": db.scalar(
            select(func.count()).select_from(Conversation).where(Conversation.workspace_id == wid)
        ),
        "tickets": db.scalar(
            select(func.count()).select_from(Ticket).where(Ticket.workspace_id == wid)
        ),
        "documents": db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.workspace_id == wid, Document.deleted.is_(False))
        ),
    }
    return {
        **counts,
        "messages_today": w.quota_used if w.quota_day == now().date().isoformat() else 0,
        "quota": w.quota_limit,
        "model_mode": settings().model_mode,
        "recent_usage": [
            row(e)
            for e in db.scalars(
                select(UsageEvent)
                .where(UsageEvent.workspace_id == wid)
                .order_by(UsageEvent.created_at.desc())
                .limit(20)
            )
        ],
    }


@app.get("/workspaces/{wid}/members")
def members(wid: str, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id)
    return [
        {"id": m.id, "user_id": u.id, "email": u.email, "role": m.role}
        for m, u in db.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.workspace_id == wid)
        )
    ]


@app.post("/workspaces/{wid}/members")
def add_member(wid: str, payload: MemberInput, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id, {"owner"})
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if not user:
        raise HTTPException(
            404, "That user must register first. Email invitations are not supported yet."
        )
    m = db.scalar(
        select(Membership).where(Membership.workspace_id == wid, Membership.user_id == user.id)
    )
    if m and m.role == "owner":
        raise HTTPException(409, "The owner role cannot be changed here.")
    if m:
        m.role = payload.role
    else:
        db.add(Membership(workspace_id=wid, user_id=user.id, role=payload.role))
    db.commit()
    return {"ok": True}


@app.delete("/workspaces/{wid}/members/{mid}")
def delete_member(wid: str, mid: str, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id, {"owner"})
    m = owned(db, Membership, wid, mid)
    if m.role == "owner":
        raise HTTPException(409, "Owner cannot be removed.")
    # Clear owned handoffs when a member is removed.
    for c in db.scalars(
        select(Conversation)
        .where(Conversation.workspace_id == wid, Conversation.agent_id == m.user_id)
        .with_for_update()
    ):
        c.agent_id, c.state, c.revision = None, "pending-human", c.revision + 1
    db.delete(m)
    db.commit()
    return {"ok": True}


@app.get("/workspaces/{wid}/documents")
def documents(wid: str, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id)
    return [
        {
            **row(doc),
            "versions": [
                {k: v for k, v in row(version).items() if k != "storage_key"}
                for version in db.scalars(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.workspace_id == wid, DocumentVersion.document_id == doc.id
                    )
                    .order_by(DocumentVersion.number.desc())
                )
            ],
        }
        for doc in db.scalars(
            select(Document).where(Document.workspace_id == wid, Document.deleted.is_(False))
        )
    ]


def upload_document(db, wid, file, document_id=None):
    filename = Path(file.filename or "document").name[:200]
    if Path(filename).suffix.lower() not in {".pdf", ".txt", ".md"}:
        raise HTTPException(422, "Upload a PDF, TXT, or Markdown file.")
    data = file.file.read(settings().max_upload_bytes + 1)
    if not data or not data.strip():
        raise HTTPException(422, "The file is empty.")
    if len(data) > settings().max_upload_bytes:
        raise HTTPException(413, "File is too large. Maximum size is 10 MB.")
    if Path(filename).suffix.lower() == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(422, "File is not a valid PDF.")
    w = db.get(Workspace, wid)
    if w.embedding_identity != settings().embedding_identity:
        raise HTTPException(
            409,
            "Embedding model changed. Restore the original configuration or create a new workspace and reupload all documents.",
        )
    if document_id:
        doc = db.scalar(
            select(Document)
            .where(
                Document.id == document_id,
                Document.workspace_id == wid,
                Document.deleted.is_(False),
            )
            .with_for_update()
        )
        if not doc:
            raise HTTPException(404, "Document not found.")
    else:
        doc = Document(workspace_id=wid, name=filename)
        db.add(doc)
        db.flush()
    number = (
        db.scalar(
            select(func.max(DocumentVersion.number)).where(DocumentVersion.document_id == doc.id)
        )
        or 0
    ) + 1
    version = DocumentVersion(
        id=uid(),
        workspace_id=wid,
        document_id=doc.id,
        number=number,
        filename=filename,
        storage_key=f"{wid}/{doc.id}/{uid()}",
        embedding_identity=w.embedding_identity,
    )
    # Persist queued metadata first; a crash is recoverable and cannot leak an untracked object.
    db.add(version)
    db.commit()
    try:
        storage.put(version.storage_key, data)
    except Exception:
        version.status, version.error = (
            "failed",
            "Object storage unavailable. Upload a replacement to retry.",
        )
        db.commit()
        raise HTTPException(
            503, "Object storage unavailable. Upload a replacement after recovery."
        ) from None
    dispatch(wid, version.id)
    return {"id": doc.id, "version_id": version.id, "status": "queued"}


@app.post("/workspaces/{wid}/documents")
def upload(
    wid: str, file: UploadFile = File(...), session=Depends(authenticated), db=Depends(get_db)
):
    member(db, wid, session.user_id, MANAGERS)
    return upload_document(db, wid, file)


@app.post("/workspaces/{wid}/documents/{did}/replace")
def replace_document(
    wid: str,
    did: str,
    file: UploadFile = File(...),
    session=Depends(authenticated),
    db=Depends(get_db),
):
    member(db, wid, session.user_id, MANAGERS)
    return upload_document(db, wid, file, did)


@app.get("/workspaces/{wid}/documents/{did}/download")
def download(wid: str, did: str, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id)
    doc = owned(db, Document, wid, did)
    if doc.deleted or not doc.active_version_id:
        raise HTTPException(404, "No active document.")
    version = db.get(DocumentVersion, doc.active_version_id)
    try:
        data = storage.get(version.storage_key)
    except Exception:
        raise HTTPException(503, "Document storage unavailable.") from None
    return Response(
        data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=document"},
    )


@app.delete("/workspaces/{wid}/documents/{did}")
def delete_document(wid: str, did: str, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id, MANAGERS)
    doc = db.scalar(
        select(Document).where(Document.workspace_id == wid, Document.id == did).with_for_update()
    )
    if not doc:
        raise HTTPException(404, "Document not found.")
    doc.deleted, doc.active_version_id = True, None
    db.commit()
    return {"ok": True, "cleanup": "scheduled"}


@app.get("/workspaces/{wid}/conversations")
def conversations(wid: str, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id)
    return [
        row(c)
        for c in db.scalars(
            select(Conversation)
            .where(Conversation.workspace_id == wid)
            .order_by(Conversation.created_at.desc())
            .limit(200)
        )
    ]


@app.post("/workspaces/{wid}/conversations")
def create_conversation(wid: str, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id)
    c = Conversation(workspace_id=wid)
    db.add(c)
    db.commit()
    return row(c)


def message_rows(db, c):
    messages = db.scalars(
        select(Message)
        .where(Message.workspace_id == c.workspace_id, Message.conversation_id == c.id)
        .order_by(Message.created_at, Message.id)
    ).all()
    return {
        **row(c),
        "messages": [
            {
                **row(m),
                "citations": [
                    {
                        "id": cite.id,
                        "document_id": cite.document_id,
                        "version_id": cite.version_id,
                        "page": cite.page,
                        "section": cite.section,
                        "available": bool(
                            (doc := db.get(Document, cite.document_id)) and not doc.deleted
                        ),
                    }
                    for cite in db.scalars(
                        select(MessageCitation).where(
                            MessageCitation.message_id == m.id,
                            MessageCitation.workspace_id == c.workspace_id,
                        )
                    )
                ],
            }
            for m in messages
        ],
    }


@app.get("/workspaces/{wid}/conversations/{cid}")
def conversation(wid: str, cid: str, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id)
    return message_rows(db, owned(db, Conversation, wid, cid))


@app.delete("/workspaces/{wid}/conversations/{cid}")
def delete_conversation(wid: str, cid: str, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id, MANAGERS)
    db.delete(owned(db, Conversation, wid, cid))
    db.commit()
    return {"ok": True}


def event(name, data):
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def stream_reply(wid, cid, payload, user_id=None, visitor_id=None, session_id=None):
    # Generate/commit before emitting text. Never expose an unverified action or partial model JSON.
    def stream():
        yield event("status", {"state": "working", "request_key": payload.request_key})
        try:
            with SessionLocal.begin() as db:
                if user_id:
                    member(db, wid, user_id)
                message, revision = run_chat(db, wid, cid, payload, visitor_id)
                result = {"id": message.id, "content": message.content, "role": message.role}
            for start in range(0, len(result["content"]), 80):
                with SessionLocal() as db:
                    c = db.get(Conversation, cid)
                    if not c or c.revision != revision:
                        yield event(
                            "interrupted",
                            {"detail": "Conversation state changed. Refresh messages."},
                        )
                        return
                    if user_id:
                        member(db, wid, user_id)
                    auth_record = (
                        db.get(Session, session_id)
                        if user_id
                        else db.get(WidgetSession, session_id)
                    )
                    if not auth_record or auth_record.expires_at <= now():
                        yield event("interrupted", {"detail": "Session expired. Sign in again."})
                        return
                yield event("delta", {"text": result["content"][start : start + 80]})
            yield event("done", {"message_id": result["id"], "request_key": payload.request_key})
        except HTTPException as exc:
            yield event("error", {"detail": exc.detail, "status": exc.status_code})
        except ProviderError as exc:
            yield event("error", {"detail": str(exc), "status": 503})
        except Exception:
            yield event(
                "error",
                {
                    "detail": "Unable to complete the message. Retry with the same request key.",
                    "status": 503,
                },
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.post("/workspaces/{wid}/conversations/{cid}/chat")
def chat(
    wid: str, cid: str, payload: ChatInput, session=Depends(authenticated), db=Depends(get_db)
):
    member(db, wid, session.user_id)
    owned(db, Conversation, wid, cid)
    rate_limit("chat:" + session.user_id, 60)
    return stream_reply(wid, cid, payload, user_id=session.user_id, session_id=session.id)


@app.post("/workspaces/{wid}/conversations/{cid}/{action}")
def human_action(
    wid: str,
    cid: str,
    action: str,
    payload: ReplyInput | None = None,
    session=Depends(authenticated),
    db=Depends(get_db),
):
    member(db, wid, session.user_id)
    c = db.scalar(
        select(Conversation)
        .where(Conversation.workspace_id == wid, Conversation.id == cid)
        .with_for_update()
    )
    if not c:
        raise HTTPException(404, "Conversation not found.")
    if action == "claim":
        if c.agent_id and c.agent_id != session.user_id:
            raise HTTPException(409, "Another agent owns this conversation.")
        c.state, c.agent_id = "human", session.user_id
    elif action in {"release", "reply"}:
        if c.state != "human" or c.agent_id != session.user_id:
            raise HTTPException(
                409, "Claim this conversation before replying or returning it to the bot."
            )
        if action == "release":
            c.state, c.agent_id = "bot", None
        elif not payload or not payload.text.strip():
            raise HTTPException(422, "Enter a reply.")
        else:
            db.add(
                Message(workspace_id=wid, conversation_id=cid, role="agent", content=payload.text)
            )
    else:
        raise HTTPException(404, "Unknown action.")
    c.revision += 1
    db.commit()
    return row(c)


@app.get("/workspaces/{wid}/tickets")
def tickets(wid: str, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id)
    return [
        row(t)
        for t in db.scalars(
            select(Ticket)
            .where(Ticket.workspace_id == wid)
            .order_by(Ticket.created_at.desc())
            .limit(200)
        )
    ]


@app.patch("/workspaces/{wid}/tickets/{tid}")
def update_ticket(
    wid: str, tid: str, payload: TicketUpdate, session=Depends(authenticated), db=Depends(get_db)
):
    member(db, wid, session.user_id)
    ticket = owned(db, Ticket, wid, tid)
    if payload.assignee_id:
        member(db, wid, payload.assignee_id)
    ticket.status, ticket.assignee_id = payload.status, payload.assignee_id
    db.commit()
    return row(ticket)


def source_content(db, wid, citation_id, visitor_id=None):
    cite = owned(db, MessageCitation, wid, citation_id)
    msg = owned(db, Message, wid, cite.message_id)
    c = owned(db, Conversation, wid, msg.conversation_id)
    if visitor_id and c.visitor_id != visitor_id:
        raise HTTPException(404, "Source not found.")
    doc = db.get(Document, cite.document_id)
    if not doc or doc.deleted:
        raise HTTPException(410, "This source is no longer available.")
    return {
        "document": doc.name,
        "version_id": cite.version_id,
        "page": cite.page,
        "section": cite.section,
        "excerpt": cite.excerpt,
    }


@app.get("/workspaces/{wid}/sources/{sid}")
def source(wid: str, sid: str, session=Depends(authenticated), db=Depends(get_db)):
    member(db, wid, session.user_id)
    return source_content(db, wid, sid)


@app.get("/public/{public_id}/config")
def public_config(public_id: str, db=Depends(get_db)):
    w = db.scalar(select(Workspace).where(Workspace.public_id == public_id))
    if not w:
        raise HTTPException(404, "Chatbot not found.")
    return {
        "name": w.name,
        "bot_name": w.bot_name,
        "welcome": w.welcome,
        "color": w.color,
        "model_mode": settings().model_mode,
    }


@app.post("/public/{public_id}/session")
def visitor_session(public_id: str, payload: VisitorInput, request: Request, db=Depends(get_db)):
    rate_limit("session:" + (request.client.host if request.client else "unknown"), 30)
    w = db.scalar(select(Workspace).where(Workspace.public_id == public_id))
    if not w or payload.origin not in w.origins:
        raise HTTPException(403, "This website is not permitted to embed the chatbot.")
    token = secrets.token_urlsafe(32)
    v = WidgetSession(
        workspace_id=w.id,
        token_hash=digest(token),
        origin=payload.origin,
        expires_at=now() + timedelta(hours=settings().visitor_hours),
    )
    db.add(v)
    db.flush()
    c = Conversation(workspace_id=w.id, visitor_id=v.id)
    db.add(c)
    db.commit()
    return {"token": token, "conversation_id": c.id, "expires_at": v.expires_at.isoformat() + "Z"}


@app.get("/visitor/conversations/{cid}")
def visitor_messages(cid: str, v=Depends(visitor), db=Depends(get_db)):
    c = owned(db, Conversation, v.workspace_id, cid)
    if c.visitor_id != v.id:
        raise HTTPException(404, "Conversation not found.")
    return message_rows(db, c)


@app.post("/visitor/conversations/{cid}/chat")
def visitor_chat(cid: str, payload: ChatInput, v=Depends(visitor), db=Depends(get_db)):
    c = owned(db, Conversation, v.workspace_id, cid)
    if c.visitor_id != v.id:
        raise HTTPException(404, "Conversation not found.")
    return stream_reply(v.workspace_id, cid, payload, visitor_id=v.id, session_id=v.id)


@app.get("/visitor/sources/{sid}")
def visitor_source(sid: str, v=Depends(visitor), db=Depends(get_db)):
    return source_content(db, v.workspace_id, sid, v.id)


WIDGET_DIR = Path(__file__).resolve().parents[2] / "widget"


@app.get("/widget/loader.js")
def loader():
    return FileResponse(WIDGET_DIR / "loader.js", media_type="application/javascript")


@app.get("/widget/{public_id}")
def widget(public_id: str, db=Depends(get_db)):
    w = db.scalar(select(Workspace).where(Workspace.public_id == public_id))
    if not w:
        raise HTTPException(404, "Chatbot not found.")
    return FileResponse(
        WIDGET_DIR / "index.html",
        headers={
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors "
            + (" ".join(w.origins) or "'none'")
        },
    )


@app.get("/widget-assets/app.js")
def widget_js():
    return FileResponse(WIDGET_DIR / "app.js", media_type="application/javascript")


@app.get("/health")
def health():
    return {"status": "ok", "model_mode": settings().model_mode}


@app.get("/ready")
def ready(db=Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        if not settings().test_memory_rate_limit:
            Redis.from_url(settings().redis_url, socket_timeout=2).ping()
        if settings().storage_mode == "s3":
            storage.client().head_bucket(Bucket=settings().s3_bucket)
    except Exception:
        raise HTTPException(
            503, "A required database, broker, or storage dependency is unavailable."
        ) from None
    return {"status": "ready", "model_mode": settings().model_mode}
