"""Development helper: generate a frozen initial migration from the model metadata."""

import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
os.environ.setdefault("DATABASE_URL", "sqlite://")
from alembic.autogenerate import produce_migrations, render_python_code
from alembic.migration import MigrationContext
from app.models import Base
from sqlalchemy import create_engine

with create_engine("sqlite://").connect() as connection:
    migration = produce_migrations(
        MigrationContext.configure(connection), Base.metadata
    )
    upgrade = render_python_code(migration.upgrade_ops)
    downgrade = render_python_code(migration.downgrade_ops)
source = (
    '''"""Initial tenant-safe schema. Frozen migration; do not import application models."""
from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
'''
    + upgrade
    + "\n\ndef downgrade():\n"
    + downgrade
    + "\n"
)
(root / "backend/migrations/versions/0001_initial.py").write_text(
    source, encoding="utf-8"
)
