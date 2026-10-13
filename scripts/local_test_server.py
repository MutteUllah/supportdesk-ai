"""Dependency-light test server, explicitly NOT the production/worker configuration."""

import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///" + str(root / "backend/browser-test.db")
os.environ["STORAGE_MODE"] = "local"
os.environ["LOCAL_STORAGE_PATH"] = str(root / "backend/.local-storage")
os.environ["MODEL_MODE"] = "mock"
os.environ["TEST_INLINE_JOBS"] = "true"
os.environ["TEST_MEMORY_RATE_LIMIT"] = "true"

import uvicorn
from alembic import command
from alembic.config import Config

command.upgrade(Config(str(root / "backend/alembic.ini")), "head")
print(
    "TEST ADAPTERS: SQLite, local files, inline jobs, mock models. Not a real worker demo."
)
uvicorn.run("app.main:app", host="127.0.0.1", port=8000, access_log=False)
