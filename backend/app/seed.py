"""Explicit, reproducible demo seeding. Never invoked by application startup."""

from sqlalchemy import select

from . import storage
from .config import settings
from .db import SessionLocal
from .ingestion import dispatch
from .models import Document, DocumentVersion, Membership, User, Workspace, uid
from .security import passwords

BUSINESSES = [
    (
        "Northstar Outfitters",
        "northstar@example.test",
        "Northstar shipping: orders arrive in 3 business days. Shipping costs $5; free on orders over $75.\nNorthstar returns: unused products may be returned within 30 days with a receipt.\nNorthstar warranty: manufacturing defects are covered for one year.",
    ),
    (
        "Cedar & Clay",
        "cedar@example.test",
        "Cedar & Clay shipping: handmade orders arrive in 12 business days. Shipping costs $12 on every order.\nCedar & Clay returns: unused products may be returned within 7 days. Custom items cannot be returned.\nCedar & Clay warranty: transit damage must be reported within 48 hours.",
    ),
]


def seed():
    cfg = settings()
    if cfg.environment == "production":
        raise SystemExit("Demo seeding is disabled in production.")
    if len(cfg.demo_password) < 12:
        raise SystemExit("Set DEMO_PASSWORD to a unique password of at least 12 characters.")
    for name, email, policy in BUSINESSES:
        with SessionLocal.begin() as db:
            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(email=email, password_hash=passwords.hash(cfg.demo_password))
                db.add(user)
                db.flush()
            w = db.scalar(
                select(Workspace)
                .join(Membership, Membership.workspace_id == Workspace.id)
                .where(Membership.user_id == user.id, Workspace.name == name)
            )
            if not w:
                w = Workspace(
                    name=name,
                    bot_name=name + " support",
                    origins=["http://localhost:3001"],
                    embedding_identity=cfg.embedding_identity,
                    quota_limit=cfg.daily_chat_quota,
                )
                db.add(w)
                db.flush()
                db.add(Membership(workspace_id=w.id, user_id=user.id, role="owner"))
                db.flush()
            doc = db.scalar(
                select(Document).where(
                    Document.workspace_id == w.id, Document.name == "demo-policy.md"
                )
            )
            if not doc:
                doc = Document(workspace_id=w.id, name="demo-policy.md")
                db.add(doc)
                db.flush()
                version = DocumentVersion(
                    id=uid(),
                    workspace_id=w.id,
                    document_id=doc.id,
                    number=1,
                    filename=doc.name,
                    storage_key=f"{w.id}/{doc.id}/{uid()}",
                    embedding_identity=w.embedding_identity,
                )
                db.add(version)
                db.flush()
                storage.put(version.storage_key, policy.encode())
                vid = version.id
            else:
                existing_vid = db.scalar(
                    select(DocumentVersion.id)
                    .where(DocumentVersion.document_id == doc.id)
                    .order_by(DocumentVersion.number.desc())
                )
                if existing_vid is None:
                    raise RuntimeError("Demo document has no version. Remove it and seed again.")
                vid = existing_vid
            wid, public = w.id, w.public_id
        dispatch(wid, vid)
        print(f"{name}: {email} | public workspace ID: {public}")


if __name__ == "__main__":
    seed()
