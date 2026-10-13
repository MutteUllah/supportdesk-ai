"""Run against disposable PostgreSQL via TEST_DATABASE_URL. SQLite cannot validate row locks."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import conversation, send
from fastapi.testclient import TestClient

from app.db import engine
from app.main import app

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql", reason="Requires PostgreSQL row locks"
)


def test_concurrent_ticket_retries(owner, workspace):
    wid = workspace["id"]
    cid = conversation(owner, wid)

    def request(_):
        with TestClient(app) as client:
            client.cookies.update(owner.cookies)
            client.headers.update(owner.headers)
            return send(
                client, wid, cid, action="ticket", consent=True, subject="One logical action"
            ).text

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(request, range(4)))
    assert all("event: done" in r for r in results)
    assert len(owner.get(f"/workspaces/{wid}/tickets").json()) == 1


def test_concurrent_agent_claims(owner, workspace):
    from conftest import account

    agent = account("agent@example.test")
    wid = workspace["id"]
    owner.post(
        f"/workspaces/{wid}/members", json={"email": "agent@example.test", "role": "support-agent"}
    )
    cid = conversation(owner, wid)

    def claim(client):
        return client.post(f"/workspaces/{wid}/conversations/{cid}/claim").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(claim, [owner, agent]))
    assert sorted(statuses) == [200, 409]
