import io
from datetime import timedelta
from pathlib import Path

from celery import Celery
from pypdf import PdfReader
from sqlalchemy import delete, select

from . import storage
from .config import settings
from .db import SessionLocal
from .models import (
    Conversation,
    Document,
    DocumentChunk,
    DocumentVersion,
    Session,
    WidgetSession,
    now,
)
from .provider import embeddings

celery = Celery("supportdesk", broker=settings().redis_url)
celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_soft_time_limit=240,
    task_time_limit=300,
    beat_schedule={"recover-and-clean": {"task": "app.ingestion.maintenance", "schedule": 60.0}},
)


def extract(data, filename):
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
        except Exception:
            raise ValueError("Invalid or encrypted PDF. Upload a text-based PDF.") from None
    elif extension in {".txt", ".md"}:
        try:
            pages = [(1, data.decode("utf-8-sig"))]
        except UnicodeDecodeError:
            raise ValueError("Text files must use UTF-8 encoding.") from None
    else:
        raise ValueError("Supported file types: PDF, TXT, Markdown.")
    if not any(text.strip() for _, text in pages):
        raise ValueError("No text found. Empty files and scanned PDFs are not supported.")
    if sum(len(text) for _, text in pages) > settings().max_document_chars:
        raise ValueError("Document contains too much text. Split it into smaller files.")
    return pages


def split(pages):
    s = settings()
    for page, text in pages:
        for start in range(0, len(text), s.chunk_size - s.chunk_overlap):
            part = text[start : start + s.chunk_size].strip()
            if part:
                yield page, part


def process_version(workspace_id, version_id):
    # Keep document lock through extraction/index swap. Replacement and deletion use the same lock.
    with SessionLocal.begin() as db:
        version = db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.id == version_id, DocumentVersion.workspace_id == workspace_id
            )
        )
        if not version:
            return
        doc = db.scalar(
            select(Document)
            .where(Document.id == version.document_id, Document.workspace_id == workspace_id)
            .with_for_update()
        )
        db.refresh(version)
        if not doc or doc.deleted or version.status == "ready":
            return
        if version.embedding_identity != settings().embedding_identity:
            raise ValueError(
                "Embedding configuration changed. Restore it or reindex into a new workspace."
            )
        version.status = "processing"
        parts = list(split(extract(storage.get(version.storage_key), version.filename)))
        vectors = []
        for start in range(0, len(parts), 32):
            vectors.extend(embeddings([text for _, text in parts[start : start + 32]]))
        db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.workspace_id == workspace_id, DocumentChunk.version_id == version.id
            )
        )
        for i, ((page, text), vector) in enumerate(zip(parts, vectors, strict=True)):
            db.add(
                DocumentChunk(
                    workspace_id=workspace_id,
                    version_id=version.id,
                    ordinal=i,
                    page=page,
                    section=f"Page {page}",
                    text=text,
                    embedding=vector,
                )
            )
        active = db.get(DocumentVersion, doc.active_version_id) if doc.active_version_id else None
        if not active or active.number < version.number:
            doc.active_version_id = version.id
        version.status, version.error, version.updated_at = "ready", None, now()


@celery.task(name="app.ingestion.ingest", bind=True, max_retries=3)
def ingest(self, workspace_id, version_id):
    with SessionLocal.begin() as db:
        version = db.scalar(
            select(DocumentVersion)
            .where(DocumentVersion.id == version_id, DocumentVersion.workspace_id == workspace_id)
            .with_for_update()
        )
        if not version or version.status == "ready" or version.attempts >= 4:
            return
        version.status, version.updated_at = "processing", now()
        version.attempts += 1
    try:
        process_version(workspace_id, version_id)
    except Exception as exc:
        permanent = isinstance(exc, ValueError)
        with SessionLocal.begin() as db:
            version = db.get(DocumentVersion, version_id)
            if version:
                version.status = "failed" if permanent or version.attempts >= 4 else "queued"
                version.error = (
                    str(exc)[:300]
                    if permanent
                    else "Ingestion dependency unavailable. Retry after checking storage and model configuration."
                )
                version.updated_at = now()
        if not permanent and self.request.retries < self.max_retries:
            raise self.retry(
                exc=RuntimeError("Ingestion temporarily unavailable"),
                countdown=2 ** (self.request.retries + 1),
            )


def dispatch(workspace_id, version_id):
    if settings().test_inline_jobs:
        ingest.apply(args=[workspace_id, version_id], throw=True)
        return
    try:
        ingest.apply_async(args=[workspace_id, version_id], retry=False)
    except Exception:
        # Durable queued record is the outbox. Beat retries dispatch after broker recovery.
        pass


@celery.task(name="app.ingestion.maintenance")
def maintenance():
    cutoff = now() - timedelta(minutes=6)
    with SessionLocal.begin() as db:
        for version in db.scalars(
            select(DocumentVersion).where(
                DocumentVersion.status.in_(["queued", "processing"]),
                DocumentVersion.updated_at < cutoff,
            )
        ):
            if version.attempts >= 4:
                version.status = "failed"
                version.error = "Retry budget exhausted. Upload a replacement to retry."
            else:
                dispatch(version.workspace_id, version.id)
        for doc in db.scalars(
            select(Document).where(Document.deleted.is_(True)).with_for_update(skip_locked=True)
        ):
            versions = db.scalars(
                select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
            ).all()
            for version in versions:
                storage.remove(
                    version.storage_key
                )  # On failure tombstone persists for the next run.
            db.delete(doc)
        db.execute(
            delete(Conversation).where(
                Conversation.created_at < now() - timedelta(days=settings().retention_days)
            )
        )
        db.execute(delete(Session).where(Session.expires_at < now()))
        # Visitors retain history for retention period, although bearer access expires earlier.
        db.execute(
            delete(WidgetSession).where(
                WidgetSession.created_at < now() - timedelta(days=settings().retention_days)
            )
        )
