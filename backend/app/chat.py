import time
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, TypedDict

from fastapi import HTTPException
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from .config import settings
from .models import (
    Conversation,
    Document,
    DocumentChunk,
    DocumentVersion,
    Message,
    MessageCitation,
    Ticket,
    ToolExecution,
    UsageEvent,
    Workspace,
    now,
)
from .provider import ProviderError, answer, embeddings, terms


class State(TypedDict, total=False):
    db: Any
    conversation: Any
    workspace: Any
    payload: Any
    sources: list
    response: dict
    history: list
    mode: str
    ticket: Any
    started: float
    message: Any


def load_context(s):
    db, c = s["db"], s["conversation"]
    history = list(
        reversed(
            db.scalars(
                select(Message)
                .where(
                    Message.workspace_id == c.workspace_id,
                    Message.conversation_id == c.id,
                    Message.role.in_(["user", "assistant"]),
                )
                .order_by(Message.created_at.desc())
                .limit(10)
            ).all()
        )
    )
    return {
        "history": [{"role": m.role, "content": m.content[:4000]} for m in history],
        "started": time.monotonic(),
    }


def route_request(s):
    p, c = s["payload"], s["conversation"]
    if p.action == "ticket" and (not p.consent or not p.subject.strip()):
        raise HTTPException(422, "Confirm ticket creation and provide a subject.")
    mode = p.action if p.action != "chat" else ("paused" if c.state != "bot" else "retrieve")
    return {"mode": mode, "sources": []}


def retrieve(s):
    if s["mode"] != "retrieve":
        return {}
    db, w, p = s["db"], s["workspace"], s["payload"]
    if w.embedding_identity != settings().embedding_identity:
        raise HTTPException(
            409, "Embedding configuration changed. Restore it or reindex into a new workspace."
        )
    question = p.text
    # Simple follow-up context in mock mode; real generation also receives bounded history.
    if len(terms(question)) < 3 and s["history"]:
        previous = next((m["content"] for m in reversed(s["history"]) if m["role"] == "user"), "")
        question = previous + " " + question
    vector = embeddings([question])[0]
    statement = (
        select(DocumentChunk)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(
            DocumentChunk.workspace_id == w.id,
            DocumentVersion.workspace_id == w.id,
            Document.workspace_id == w.id,
            Document.deleted.is_(False),
            Document.active_version_id == DocumentChunk.version_id,
            DocumentVersion.status == "ready",
            DocumentVersion.embedding_identity == w.embedding_identity,
        )
    )
    max_distance = 0.99 if settings().model_mode == "mock" else settings().retrieval_max_distance
    if db.bind.dialect.name == "postgresql":
        distance = DocumentChunk.embedding.cosine_distance(vector)
        candidates = db.scalars(
            statement.where(distance < max_distance)
            .order_by(distance)
            .limit(settings().retrieval_count)
        ).all()
    else:
        candidates = db.scalars(statement).all()
        candidates.sort(key=lambda c: sum(a * b for a, b in zip(c.embedding, vector)), reverse=True)
        candidates = [
            c
            for c in candidates
            if sum(a * b for a, b in zip(c.embedding, vector)) > 1 - max_distance
        ][: settings().retrieval_count]
    if settings().model_mode == "mock":
        candidates = [c for c in candidates if terms(question) & terms(c.text)]
    # Give the model only the exact bounded excerpt that the customer can inspect.
    # Do not mutate ORM chunk.text: doing so would persist accidental truncation.
    evidence = []
    for chunk in candidates:
        windows = [chunk.text[i : i + 500] for i in range(0, len(chunk.text), 250)]
        excerpt = max(windows, key=lambda window: len(terms(question) & terms(window)))
        evidence.append(
            SimpleNamespace(
                id=chunk.id,
                version_id=chunk.version_id,
                page=chunk.page,
                section=chunk.section,
                text=excerpt,
            )
        )
    return {"sources": evidence}


def generate(s):
    if s["mode"] == "retrieve" and s["sources"]:
        response = answer(s["payload"].text, s["history"], s["sources"])
    elif s["mode"] == "retrieve":
        response = {
            "answer": "I couldn't find enough information in this business's documents. Could you clarify your question? You can also create a support ticket or request a human.",
            "citations": [],
        }
    elif s["mode"] == "paused":
        response = {"answer": "Your message has been saved for the support team.", "citations": []}
    else:
        response = {"answer": "", "citations": []}
    return {"response": response}


def validate_citations(s):
    allowed = {c.id for c in s["sources"]}
    result = s["response"]
    refs = result.get("citations", [])
    if any(not isinstance(ref, str) or ref not in allowed for ref in refs):
        raise ProviderError("Model cited an unavailable source. Please retry.")
    if s["mode"] == "retrieve" and s["sources"] and not refs:
        result["answer"] = (
            "The available sources do not support an answer. Please clarify, create a ticket, or request a human."
        )
    return {"response": result}


def execute_tool(s):
    db, c, p = s["db"], s["conversation"], s["payload"]
    if s["mode"] == "ticket":
        # Only explicit structured consent reaches this branch. Model output cannot select tools.
        ticket = db.scalar(
            select(Ticket).where(
                Ticket.workspace_id == c.workspace_id,
                Ticket.conversation_id == c.id,
                Ticket.action_key == p.request_key,
            )
        )
        if ticket is None:
            ticket = Ticket(
                workspace_id=c.workspace_id,
                conversation_id=c.id,
                action_key=p.request_key,
                subject=p.subject,
                description=p.text,
                email=p.email,
            )
            db.add(ticket)
            db.flush()
            db.add(
                ToolExecution(
                    workspace_id=c.workspace_id,
                    conversation_id=c.id,
                    action_key=p.request_key,
                    ticket_id=ticket.id,
                    verified=False,
                )
            )
            db.flush()
        return {"ticket": ticket}
    if s["mode"] == "handoff":
        if c.state == "bot":
            c.state = "pending-human"
            c.revision += 1
        return {
            "response": {
                "answer": "Your request is queued for a human. An agent has not joined yet."
                if c.state == "pending-human"
                else "A support agent controls this conversation.",
                "citations": [],
            }
        }
    return {}


def verify_tool(s):
    if s["mode"] != "ticket":
        return {}
    db, c, ticket = s["db"], s["conversation"], s["ticket"]
    found = db.scalar(
        select(Ticket).where(
            Ticket.id == ticket.id,
            Ticket.workspace_id == c.workspace_id,
            Ticket.conversation_id == c.id,
        )
    )
    if not found:
        raise HTTPException(503, "Ticket could not be verified. Retry with the same request key.")
    execution = db.scalar(
        select(ToolExecution).where(
            ToolExecution.conversation_id == c.id,
            ToolExecution.action_key == s["payload"].request_key,
        )
    )
    execution.verified = True
    return {"response": {"answer": f"Support ticket {found.id} was created.", "citations": []}}


def save_result(s):
    db, c, p, result = s["db"], s["conversation"], s["payload"], s["response"]
    timestamp = now()
    db.add(
        Message(
            workspace_id=c.workspace_id,
            conversation_id=c.id,
            role="user",
            content=p.text,
            request_key=p.request_key,
            created_at=timestamp,
        )
    )
    message = Message(
        workspace_id=c.workspace_id,
        conversation_id=c.id,
        role="system" if s["mode"] == "paused" else "assistant",
        content=result["answer"],
        request_key=p.request_key,
        created_at=timestamp + timedelta(microseconds=1),
    )
    db.add(message)
    db.flush()
    for chunk in s["sources"]:
        if chunk.id in result.get("citations", []):
            version = db.get(DocumentVersion, chunk.version_id)
            db.add(
                MessageCitation(
                    workspace_id=c.workspace_id,
                    message_id=message.id,
                    document_id=version.document_id,
                    version_id=version.id,
                    chunk_id=chunk.id,
                    page=chunk.page,
                    section=chunk.section,
                    excerpt=chunk.text[:500],
                )
            )
    cfg = settings()
    inp, out = result.get("input_tokens", 0), result.get("output_tokens", 0)
    db.add(
        UsageEvent(
            workspace_id=c.workspace_id,
            model="mock-extractive" if cfg.model_mode == "mock" else cfg.chat_model,
            input_tokens=inp,
            output_tokens=out,
            latency_ms=int((time.monotonic() - s["started"]) * 1000),
            estimated_cost=(inp * cfg.input_cost_per_million + out * cfg.output_cost_per_million)
            / 1_000_000,
        )
    )
    return {"message": message}


builder = StateGraph(State)
nodes = [
    load_context,
    route_request,
    retrieve,
    generate,
    validate_citations,
    execute_tool,
    verify_tool,
    save_result,
]
previous = START
for node in nodes:
    builder.add_node(node.__name__, node)
    builder.add_edge(previous, node.__name__)
    previous = node.__name__
builder.add_edge(previous, END)
graph = builder.compile()


def run_chat(db, workspace_id, conversation_id, payload, visitor_id=None):
    # Consistent lock order: workspace then conversation. Locks serialize quotas, retries and takeover.
    w = db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    c = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.workspace_id == workspace_id)
        .with_for_update()
    )
    if c is None or (visitor_id is not None and c.visitor_id != visitor_id):
        raise HTTPException(404, "Conversation not found.")
    existing = db.scalar(
        select(Message).where(
            Message.conversation_id == c.id,
            Message.request_key == payload.request_key,
            Message.role != "user",
        )
    )
    if existing:
        return existing, c.revision
    day = now().date().isoformat()
    if w.quota_day != day:
        w.quota_day, w.quota_used = day, 0
    if w.quota_used >= w.quota_limit:
        raise HTTPException(429, "This workspace's daily message quota is reached.")
    w.quota_used += 1
    result = graph.invoke({"db": db, "workspace": w, "conversation": c, "payload": payload})
    return result["message"], c.revision
