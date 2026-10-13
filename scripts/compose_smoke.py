"""Run after docker compose up --build -d --wait. Exercises real worker/S3/Redis/pgvector."""

import time
import uuid

import httpx

with httpx.Client(
    base_url="http://localhost:8000",
    headers={"Origin": "http://localhost:3000"},
    timeout=120,
) as client:
    r = client.post(
        "/auth/register",
        json={
            "email": f"smoke-{uuid.uuid4()}@example.test",
            "password": uuid.uuid4().hex,
        },
    )
    r.raise_for_status()
    client.headers["X-CSRF-Token"] = r.json()["csrf"]
    w = client.post("/workspaces", json={"name": "Compose smoke"}).json()["id"]
    r = client.post(
        f"/workspaces/{w}/documents",
        files={
            "file": (
                "policy.md",
                b"Shipping takes 3 business days. Returns accepted within 30 days.",
            )
        },
    )
    r.raise_for_status()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        documents = client.get(f"/workspaces/{w}/documents").json()
        status = documents[0]["versions"][0]["status"]
        if status == "ready":
            break
        if status == "failed":
            raise RuntimeError(documents[0]["versions"][0]["error"])
        time.sleep(2)
    else:
        raise RuntimeError(
            "Worker did not produce a searchable document in 120 seconds"
        )
    cid = client.post(f"/workspaces/{w}/conversations").json()["id"]
    r = client.post(
        f"/workspaces/{w}/conversations/{cid}/chat",
        json={"text": "How long does shipping take?", "request_key": str(uuid.uuid4())},
    )
    assert "event: done" in r.text, r.text
    messages = client.get(f"/workspaces/{w}/conversations/{cid}").json()["messages"]
    assert messages[-1]["citations"], messages
    print("PASS: real worker -> object storage -> embeddings -> pgvector -> cited chat")
